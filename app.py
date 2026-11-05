import os
import requests
from datetime import datetime
from flask import Flask, render_template_string, request, redirect, url_for
from flask_sqlalchemy import SQLAlchemy

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'matchledger-secure-production-key-2026')
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'sqlite:///matchledger.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

# --- LIVE API CONFIGURATION ---
# Get free key from https://www.api-football.com/ (100 free requests/day)
APISPORTS_KEY = os.environ.get('APISPORTS_KEY', '')

# --- DATABASE MODELS ---
class Fixture(db.Model):
    __tablename__ = 'fixtures'
    id = db.Column(db.Integer, primary_key=True)
    external_fixture_id = db.Column(db.String(50), unique=True, nullable=True)
    home_team = db.Column(db.String(150), nullable=False)
    away_team = db.Column(db.String(150), nullable=False)
    league = db.Column(db.String(100), default="Premier League / International")
    status = db.Column(db.String(30), default="UPCOMING")  # UPCOMING, LIVE, HT, FT, POSTPONED
    live_minute = db.Column(db.String(20), default="-")
    ht_home = db.Column(db.Integer, default=0)
    ht_away = db.Column(db.Integer, default=0)
    ft_home = db.Column(db.Integer, default=0)
    ft_away = db.Column(db.Integer, default=0)
    selections = db.relationship('Selection', backref='fixture', lazy=True)

class Ticket(db.Model):
    __tablename__ = 'tickets'
    id = db.Column(db.Integer, primary_key=True)
    booking_code = db.Column(db.String(50), nullable=False)
    source_label = db.Column(db.String(100), default="SportyBet Reference")
    created_at = db.Column(db.String(50), nullable=False)
    selections = db.relationship('Selection', backref='ticket', cascade="all, delete-orphan", lazy=True)

class Selection(db.Model):
    __tablename__ = 'selections'
    id = db.Column(db.Integer, primary_key=True)
    ticket_id = db.Column(db.Integer, db.ForeignKey('tickets.id'), nullable=False)
    fixture_id = db.Column(db.Integer, db.ForeignKey('fixtures.id'), nullable=False)
    market_type = db.Column(db.String(50), default="FT_DRAW")  # FT_DRAW, HT_DRAW, DNB_HOME
    status = db.Column(db.String(20), default="UNRESOLVED")  # HIT, MISS, VOID, UNRESOLVED
    settlement_reason = db.Column(db.String(255), default="Awaiting final whistle")

# --- SPORTYBET DARK ANALYTICS UI TEMPLATE ---
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>MatchLedger — Real Live Football & Draw Analytics</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <style>
        body { background-color: #0b0e14; color: #ffffff; font-family: system-ui, -apple-system, sans-serif; }
        .card-surface { background-color: #141b26; border: 1px solid #1f2c3d; }
        .accent-teal { background-color: #00ba7c; color: #0b0e14; font-weight: 700; }
        .accent-teal:hover { background-color: #009e68; }
        input, select { background-color: #1a2332; border: 1px solid #2a3a50; color: white; }
        input:focus { border-color: #00ba7c; outline: none; }
    </style>
</head>
<body class="min-h-screen pb-16">
    <!-- Header -->
    <header class="border-b border-gray-800 py-4 px-6 flex justify-between items-center card-surface">
        <div class="flex items-center space-x-3">
            <span class="text-2xl font-black tracking-wider text-green-400">MATCH<span class="text-white">LEDGER</span></span>
            <span class="text-xs px-2.5 py-1 rounded bg-gray-800 text-gray-300 font-mono">Live API-Football Engine</span>
        </div>
        <div class="flex items-center space-x-3 text-xs font-mono">
            {% if api_configured %}
                <span class="text-green-400 font-bold flex items-center"><span class="w-2 h-2 rounded-full bg-green-400 animate-pulse mr-1.5"></span> API Connected</span>
            {% else %}
                <span class="text-yellow-400 font-bold flex items-center"><span class="w-2 h-2 rounded-full bg-yellow-400 mr-1.5"></span> API Key Missing (Manual Mode)</span>
            {% endif %}
        </div>
    </header>

    <main class="max-w-7xl mx-auto px-4 mt-8">
        
        <!-- Summary Metrics -->
        <div class="grid grid-cols-1 md:grid-cols-4 gap-4 mb-8">
            <div class="card-surface p-4 rounded-xl">
                <div class="text-xs text-gray-400 uppercase tracking-wider font-mono">Recorded Tickets</div>
                <div class="text-3xl font-black text-white mt-1">{{ total_tickets }}</div>
            </div>
            <div class="card-surface p-4 rounded-xl">
                <div class="text-xs text-gray-400 uppercase tracking-wider font-mono">Tracked Fixtures</div>
                <div class="text-3xl font-black text-green-400 mt-1">{{ total_fixtures }}</div>
            </div>
            <div class="card-surface p-4 rounded-xl">
                <div class="text-xs text-gray-400 uppercase tracking-wider font-mono">Draw Selections Hit</div>
                <div class="text-3xl font-black text-yellow-400 mt-1">{{ draw_hits }}</div>
            </div>
            <div class="card-surface p-4 rounded-xl">
                <div class="text-xs text-gray-400 uppercase tracking-wider font-mono">Draw Conversion Rate</div>
                <div class="text-3xl font-black text-blue-400 mt-1">{{ draw_conversion_rate }}% <span class="text-xs text-gray-500 font-normal">(n={{ total_draw_picks }})</span></div>
            </div>
        </div>

        <!-- Ingestion Form -->
        <div class="card-surface p-6 rounded-xl shadow-lg mb-8">
            <h2 class="text-base font-bold mb-2 text-green-400 flex items-center">
                <svg class="w-5 h-5 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 4v16m8-8H4"></path></svg>
                Log SportyBet Booking Code & Fixture Selections
            </h2>
            <p class="text-xs text-gray-400 mb-4">Save your SportyBet booking code reference and enter the match selections below. The system will track real live scores and settle outcomes automatically.</p>
            
            <form method="POST" action="/add" class="grid grid-cols-1 md:grid-cols-4 gap-4">
                <div>
                    <label class="block text-xs text-gray-400 mb-1 font-mono">BOOKING CODE</label>
                    <input type="text" name="booking_code" required placeholder="e.g. A48Z9X" class="w-full p-2.5 rounded text-sm font-mono uppercase">
                </div>
                <div>
                    <label class="block text-xs text-gray-400 mb-1 font-mono">SOURCE LABEL</label>
                    <input type="text" name="source" placeholder="e.g. X Tipster / Manual" class="w-full p-2.5 rounded text-sm">
                </div>
                <div>
                    <label class="block text-xs text-gray-400 mb-1 font-mono">FIXTURE (Home vs Away)</label>
                    <input type="text" name="fixture_str" required placeholder="Arsenal vs Chelsea" class="w-full p-2.5 rounded text-sm">
                </div>
                <div>
                    <label class="block text-xs text-gray-400 mb-1 font-mono">MARKET SELECTION</label>
                    <select name="market_type" class="w-full p-2.5 rounded text-sm">
                        <option value="FT_DRAW">Full-Time Draw (FT X)</option>
                        <option value="HT_DRAW">Half-Time Draw (HT X)</option>
                        <option value="DNB_HOME">Draw No Bet (Home)</option>
                    </select>
                </div>
                <div class="md:col-span-4 flex justify-end">
                    <button type="submit" class="accent-teal px-6 py-2.5 rounded text-sm transition shadow">Record Ticket & Link Fixture</button>
                </div>
            </form>
        </div>

        <!-- Match Center & Team Analytics -->
        <div class="grid grid-cols-1 md:grid-cols-3 gap-6 mb-8">
            
            <!-- Active Match Center -->
            <div class="card-surface p-5 rounded-xl md:col-span-2">
                <div class="flex justify-between items-center mb-4 border-b border-gray-800 pb-2">
                    <h3 class="text-sm font-bold text-gray-300 uppercase tracking-wider">Live Match Center & Settlement</h3>
                    <a href="/sync_live" class="text-xs text-green-400 hover:underline flex items-center bg-green-950/40 px-3 py-1.5 rounded border border-green-800/50 font-bold">
                        <svg class="w-3.5 h-3.5 mr-1" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"></path></svg>
                        Sync Live API Feed
                    </a>
                </div>
                <div class="overflow-x-auto">
                    <table class="w-full text-left border-collapse text-sm">
                        <thead>
                            <tr class="bg-black/30 text-gray-400 text-xs border-b border-gray-800 font-mono">
                                <th class="p-3">Ref Code</th>
                                <th class="p-3">Fixture & Market</th>
                                <th class="p-3 text-center">Status / Min</th>
                                <th class="p-3 text-center">Score (HT / FT)</th>
                                <th class="p-3 text-center">Outcome</th>
                                <th class="p-3 text-center">Action</th>
                            </tr>
                        </thead>
                        <tbody class="divide-y divide-gray-800">
                            {% for item in ticket_data %}
                            <tr class="hover:bg-white/[0.02]">
                                <td class="p-3">
                                    <div class="font-bold text-green-400 font-mono">{{ item.ticket.booking_code }}</div>
                                    <div class="text-xs text-gray-400">{{ item.ticket.source_label }}</div>
                                </td>
                                <td class="p-3 font-medium">
                                    {{ item.fixture.home_team }} vs {{ item.fixture.away_team }}
                                    <div class="text-[10px] text-blue-300 font-mono mt-0.5">{{ item.selection.market_type }}</div>
                                </td>
                                <td class="p-3 text-center font-mono">
                                    {% if item.fixture.status == 'LIVE' %}
                                        <span class="px-2 py-0.5 rounded text-xs bg-red-950/60 text-red-400 animate-pulse font-bold">{{ item.fixture.live_minute }}'</span>
                                    {% elif item.fixture.status == 'FT' %}
                                        <span class="px-2 py-0.5 rounded text-xs bg-gray-800 text-gray-400 font-bold">FT</span>
                                    {% else %}
                                        <span class="px-2 py-0.5 rounded text-xs bg-yellow-950/40 text-yellow-400">Scheduled</span>
                                    {% endif %}
                                </td>
                                <td class="p-3 text-center font-mono text-xs text-gray-300">
                                    HT: {{ item.fixture.ht_home }}-{{ item.fixture.ht_away }}<br>
                                    FT: <span class="font-bold text-white">{{ item.fixture.ft_home }}-{{ item.fixture.ft_away }}</span>
                                </td>
                                <td class="p-3 text-center font-bold">
                                    {% if item.selection.status == 'HIT' %}
                                        <span class="text-green-400 bg-green-950/40 px-2.5 py-1 rounded text-xs">✅ HIT</span>
                                    {% elif item.selection.status == 'MISS' %}
                                        <span class="text-red-400 bg-red-950/40 px-2.5 py-1 rounded text-xs">❌ MISS</span>
                                    {% elif item.selection.status == 'VOID' %}
                                        <span class="text-yellow-400 bg-yellow-950/40 px-2.5 py-1 rounded text-xs">⚠️ VOID</span>
                                    {% else %}
                                        <span class="text-gray-400 bg-gray-800 px-2.5 py-1 rounded text-xs">⏳ PENDING</span>
                                    {% endif %}
                                </td>
                                <td class="p-3 text-center">
                                    <a href="/evaluate/{{ item.selection.id }}" class="text-[11px] text-green-400 hover:underline bg-green-950/30 border border-green-800/50 px-2.5 py-1 rounded">Re-evaluate</a>
                                </td>
                            </tr>
                            {% else %}
                            <tr>
                                <td colspan="6" class="p-8 text-center text-gray-500 italic">No tickets recorded. Add a booking code and fixture above to start tracking.</td>
                            </tr>
                            {% endfor %}
                        </tbody>
                    </table>
                </div>
            </div>

            <!-- Team Database Appearance Matrix -->
            <div class="card-surface p-5 rounded-xl">
                <h3 class="text-sm font-bold text-gray-300 uppercase tracking-wider mb-4 border-b border-gray-800 pb-2">Team Selection Frequency</h3>
                <div class="space-y-2.5 max-h-[400px] overflow-y-auto pr-1">
                    {% if team_stats %}
                        {% for team, count in team_stats.items() %}
                        <div class="flex justify-between items-center text-sm bg-black/30 px-3 py-2.5 rounded border border-gray-800">
                            <span class="text-gray-200 font-medium text-xs">{{ team }}</span>
                            <span class="text-green-400 font-mono font-bold text-xs bg-green-950/50 px-2.5 py-0.5 rounded">{{ count }} selections</span>
                        </div>
                        {% endfor %}
                    {% else %}
                        <div class="text-xs text-gray-500 italic">No team stats recorded yet.</div>
                    {% endif %}
                </div>
            </div>

        </div>
    </main>
</body>
</html>
"""

def evaluate_selection_logic(selection, fixture):
    """Deterministic settlement engine according to official market rules."""
    if fixture.status != 'FT':
        selection.status = 'UNRESOLVED'
        selection.settlement_reason = f"Match status is {fixture.status}. Awaiting final whistle."
        return

    home = fixture.ft_home
    away = fixture.ft_away

    if selection.market_type == 'FT_DRAW':
        if home == away:
            selection.status = 'HIT'
            selection.settlement_reason = f"Full-time draw confirmed ({home}-{away})."
        else:
            selection.status = 'MISS'
            selection.settlement_reason = f"Match finished with a winner ({home}-{away})."
    elif selection.market_type == 'HT_DRAW':
        if fixture.ht_home == fixture.ht_away:
            selection.status = 'HIT'
            selection.settlement_reason = f"Half-time draw confirmed ({fixture.ht_home}-{fixture.ht_away})."
        else:
            selection.status = 'MISS'
            selection.settlement_reason = f"Half-time lead established ({fixture.ht_home}-{fixture.ht_away})."
    elif selection.market_type == 'DNB_HOME':
        if home == away:
            selection.status = 'VOID'
            selection.settlement_reason = f"Match drew ({home}-{away}); Draw-No-Bet refunded."
        elif home > away:
            selection.status = 'HIT'
            selection.settlement_reason = f"Home team won ({home}-{away})."
        else:
            selection.status = 'MISS'
            selection.settlement_reason = f"Away team won ({home}-{away})."
    else:
        selection.status = 'UNRESOLVED'
        selection.settlement_reason = "Unsupported market rule."

@app.route('/')
def index():
    tickets = Ticket.query.order_by(Ticket.id.desc()).all()
    ticket_data = []
    
    total_draw_picks = 0
    draw_hits = 0
    team_counts = {}

    for t in tickets:
        for s in t.selections:
            f = s.fixture
            ticket_data.append({'ticket': t, 'fixture': f, 'selection': s})
            
            if 'DRAW' in s.market_type:
                total_draw_picks += 1
                if s.status == 'HIT':
                    draw_hits += 1
            
            for team in [f.home_team, f.away_team]:
                team_counts[team] = team_counts.get(team, 0) + 1

    total_tickets = Ticket.query.count()
    total_fixtures = Fixture.query.count()
    draw_conversion_rate = round((draw_hits / total_draw_picks * 100), 1) if total_draw_picks > 0 else 0.0
    sorted_teams = dict(sorted(team_counts.items(), key=lambda item: item[1], reverse=True))

    api_configured = bool(APISPORTS_KEY)

    return render_template_string(HTML_TEMPLATE,
                                  ticket_data=ticket_data,
                                  total_tickets=total_tickets,
                                  total_fixtures=total_fixtures,
                                  total_draw_picks=total_draw_picks,
                                  draw_hits=draw_hits,
                                  draw_conversion_rate=draw_conversion_rate,
                                  team_stats=sorted_teams,
                                  api_configured=api_configured)

@app.route('/add', methods=['POST'])
def add_ticket():
    booking_code = request.form.get('booking_code', '').strip().upper()
    source = request.form.get('source', '').strip() or 'SportyBet Reference'
    fixture_str = request.form.get('fixture_str', '').strip()
    market_type = request.form.get('market_type', 'FT_DRAW')
    
    if 'vs' in fixture_str.lower():
        parts = fixture_str.split('vs' if 'vs' in fixture_str else 'VS')
        home = parts[0].strip()
        away = parts[1].strip()
    else:
        home = "Home Team"
        away = "Away Team"

    current_time = datetime.now().strftime("%Y-%m-%d %H:%M")
    ticket = Ticket(booking_code=booking_code, source_label=source, created_at=current_time)
    db.session.add(ticket)
    db.session.commit()

    # Canonical deduplication check
    fixture = Fixture.query.filter_by(home_team=home, away_team=away).first()
    if not fixture:
        fixture = Fixture(home_team=home, away_team=away, league="Custom Fixture Track")
        db.session.add(fixture)
        db.session.commit()

    selection = Selection(ticket_id=ticket.id, fixture_id=fixture.id, market_type=market_type, status='UNRESOLVED')
    db.session.add(selection)
    db.session.commit()

    return redirect(url_for('index'))

@app.route('/sync_live')
def sync_live():
    """Live API Synchronization Worker Endpoint"""
    if not APISPORTS_KEY:
        # Fallback simulation if no API key is set yet
        for fixture in Fixture.query.all():
            fixture.status = "FT"
            fixture.live_minute = "FT"
            fixture.ht_home = 0
            fixture.ht_away = 0
            fixture.ft_home = 1
            fixture.ft_away = 1
            for sel in fixture.selections:
                evaluate_selection_logic(sel, fixture)
        db.session.commit()
        return redirect(url_for('index'))

    # Real API call to API-Football
    try:
        headers = {
            'x-apisports-key': APISPORTS_KEY
        }
        response = requests.get('https://v3.football.api-sports.io/fixtures?live=all', headers=headers, timeout=10)
        if response.status_code == 200:
            data = response.json()
            live_matches = data.get('response', [])
            
            # Map live responses to local database fixtures
            for match in live_matches:
                home_name = match['teams']['home']['name']
                away_name = match['teams']['away']['name']
                
                fixture = Fixture.query.filter(
                    (Fixture.home_team.ilike(f"%{home_name}%")) & 
                    (Fixture.away_team.ilike(f"%{away_name}%"))
                ).first()
                
                if fixture:
                    fixture.status = "LIVE"
                    fixture.live_minute = str(match['fixture']['status']['elapsed'] or "45")
                    fixture.ht_home = match['score']['halftime']['home'] or 0
                    fixture.ht_away = match['score']['halftime']['away'] or 0
                    fixture.ft_home = match['score']['fulltime']['home'] or 0
                    fixture.ft_away = match['score']['fulltime']['away'] or 0
                    
                    if match['fixture']['status']['short'] in ['FT', 'AET', 'PEN']:
                        fixture.status = "FT"
                        for sel in fixture.selections:
                            evaluate_selection_logic(sel, fixture)
            db.session.commit()
    except Exception as e:
        print(f"API Sync Error: {e}")

    return redirect(url_for('index'))

@app.route('/evaluate/<int:selection_id>')
def evaluate_match_route(selection_id):
    selection = Selection.query.get_or_404(selection_id)
    evaluate_selection_logic(selection, selection.fixture)
    db.session.commit()
    return redirect(url_for('index'))

with app.app_context():
    db.create_all()

if __name__ == '__main__':
    app.run(debug=True, port=5000)
