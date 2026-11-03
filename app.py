import os
from datetime import datetime
from flask import Flask, render_template_string, request, redirect, url_for
from flask_sqlalchemy import SQLAlchemy

app = Flask(__name__)
app.config['SECRET_KEY'] = 'matchledger-secure-production-key'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///matchledger.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

# --- DATABASE MODELS ---
class Fixture(db.Model):
    __tablename__ = 'fixtures'
    id = db.Column(db.Integer, primary_key=True)
    home_team = db.Column(db.String(150), nullable=False)
    away_team = db.Column(db.String(150), nullable=False)
    league = db.Column(db.String(100), default="Premier League")
    status = db.Column(db.String(30), default="UPCOMING") # UPCOMING, LIVE, FT
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
    source_label = db.Column(db.String(100), default="Manual Input")
    created_at = db.Column(db.String(50), nullable=False)
    selections = db.relationship('Selection', backref='ticket', cascade="all, delete-orphan", lazy=True)

class Selection(db.Model):
    __tablename__ = 'selections'
    id = db.Column(db.Integer, primary_key=True)
    ticket_id = db.Column(db.Integer, db.ForeignKey('tickets.id'), nullable=False)
    fixture_id = db.Column(db.Integer, db.ForeignKey('fixtures.id'), nullable=False)
    market_type = db.Column(db.String(50), nullable=False) # FT_DRAW, HT_DRAW, DNB_HOME, etc.
    status = db.Column(db.String(20), default="UNRESOLVED") # HIT, MISS, VOID, UNRESOLVED
    settlement_reason = db.Column(db.String(255), default="Awaiting final whistle")

# --- HTML TEMPLATE (SportyBet Calm Analytical Dark Theme) ---
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>MatchLedger — Ticket Journal & Draw Analytics</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <style>
        body { background-color: #0b0e14; color: #ffffff; font-family: system-ui, -apple-system, sans-serif; }
        .card-surface { background-color: #141b26; border: 1px solid #1f2c3d; }
        .accent-teal { background-color: #00ba7c; color: #0b0e14; font-weight: 700; }
        .accent-teal:hover { background-color: #009e68; }
        input, select { background-color: #1a2332; border: 1px solid #2a3a50; color: white; }
        input:focus, select:focus { border-color: #00ba7c; outline: none; }
    </style>
</head>
<body class="min-h-screen pb-16">
    <!-- Header -->
    <header class="border-b border-gray-800 py-4 px-6 flex justify-between items-center card-surface">
        <div class="flex items-center space-x-3">
            <span class="text-2xl font-black tracking-wider text-green-400">MATCH<span class="text-white">LEDGER</span></span>
            <span class="text-xs px-2.5 py-1 rounded bg-gray-800 text-gray-300 font-mono">Quddus Workspace</span>
        </div>
        <div class="text-xs text-gray-400 font-mono">Timezone: Africa/Lagos (UTC+1) | Status: <span class="text-green-400 font-bold">Connected</span></div>
    </header>

    <main class="max-w-7xl mx-auto px-4 mt-8">
        
        <!-- Metrics Bar -->
        <div class="grid grid-cols-1 md:grid-cols-4 gap-4 mb-8">
            <div class="card-surface p-4 rounded-xl">
                <div class="text-xs text-gray-400 uppercase tracking-wider">Total Tickets</div>
                <div class="text-3xl font-black text-white mt-1">{{ total_tickets }}</div>
            </div>
            <div class="card-surface p-4 rounded-xl">
                <div class="text-xs text-gray-400 uppercase tracking-wider">Tracked Fixtures</div>
                <div class="text-3xl font-black text-green-400 mt-1">{{ total_fixtures }}</div>
            </div>
            <div class="card-surface p-4 rounded-xl">
                <div class="text-xs text-gray-400 uppercase tracking-wider">Draw Selections Hit</div>
                <div class="text-3xl font-black text-yellow-400 mt-1">{{ draw_hits }}</div>
            </div>
            <div class="card-surface p-4 rounded-xl">
                <div class="text-xs text-gray-400 uppercase tracking-wider">Draw Conversion Rate</div>
                <div class="text-3xl font-black text-blue-400 mt-1">{{ draw_conversion_rate }}% <span class="text-xs text-gray-500 font-normal">(n={{ total_draw_picks }})</span></div>
            </div>
        </div>

        <!-- Ticket Ingestion Form -->
        <div class="card-surface p-6 rounded-xl shadow-lg mb-8">
            <h2 class="text-base font-bold mb-4 text-green-400 flex items-center">
                <svg class="w-5 h-5 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 4v16m8-8H4"></path></svg>
                Log SportyBet Reference & Selections
            </h2>
            <form method="POST" action="/add" class="grid grid-cols-1 md:grid-cols-4 gap-4">
                <div>
                    <label class="block text-xs text-gray-400 mb-1 font-mono">SPORTYBET BOOKING CODE</label>
                    <input type="text" name="booking_code" required placeholder="e.g. A48Z9X" class="w-full p-2.5 rounded text-sm font-mono">
                </div>
                <div>
                    <label class="block text-xs text-gray-400 mb-1 font-mono">SOURCE / TIPSTER</label>
                    <input type="text" name="source" placeholder="e.g. X Community / Manual" class="w-full p-2.5 rounded text-sm">
                </div>
                <div>
                    <label class="block text-xs text-gray-400 mb-1 font-mono">FIXTURE (Home vs Away)</label>
                    <input type="text" name="fixture_str" required placeholder="Arsenal vs Chelsea" class="w-full p-2.5 rounded text-sm">
                </div>
                <div>
                    <label class="block text-xs text-gray-400 mb-1 font-mono">MARKET TYPE</label>
                    <select name="market_type" class="w-full p-2.5 rounded text-sm">
                        <option value="FT_DRAW">Full-Time Draw (FT X)</option>
                        <option value="HT_DRAW">Half-Time Draw (HT X)</option>
                        <option value="DNB_HOME">Draw No Bet (Home)</option>
                        <option value="DC_1X">Double Chance (1X)</option>
                    </select>
                </div>
                <div class="md:col-span-4 flex justify-end">
                    <button type="submit" class="accent-teal px-6 py-2.5 rounded text-sm transition shadow">Record Ticket & Canonical Fixture</button>
                </div>
            </form>
        </div>

        <!-- Analytics & Team Draw Frequencies -->
        <div class="grid grid-cols-1 md:grid-cols-3 gap-6 mb-8">
            <div class="card-surface p-5 rounded-xl md:col-span-2">
                <h3 class="text-sm font-bold text-gray-300 uppercase tracking-wider mb-4 border-b border-gray-800 pb-2">Active Tickets & Match Center</h3>
                <div class="overflow-x-auto">
                    <table class="w-full text-left border-collapse text-sm">
                        <thead>
                            <tr class="bg-black/30 text-gray-400 text-xs border-b border-gray-800 font-mono">
                                <th class="p-3">Ref / Source</th>
                                <th class="p-3">Fixture</th>
                                <th class="p-3">Market</th>
                                <th class="p-3 text-center">Score (HT/FT)</th>
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
                                <td class="p-3 font-medium">{{ item.fixture.home_team }} vs {{ item.fixture.away_team }}</td>
                                <td class="p-3 font-mono text-xs text-blue-300">{{ item.selection.market_type }}</td>
                                <td class="p-3 text-center font-mono text-xs text-gray-300">
                                    HT: {{ item.fixture.ht_home }}-{{ item.fixture.ht_away }}<br>
                                    FT: {{ item.fixture.ft_home }}-{{ item.fixture.ft_away }}
                                </td>
                                <td class="p-3 text-center font-bold">
                                    {% if item.selection.status == 'HIT' %}
                                        <span class="text-green-400 bg-green-950/40 px-2 py-1 rounded text-xs">✅ HIT</span>
                                    {% elif item.selection.status == 'MISS' %}
                                        <span class="text-red-400 bg-red-950/40 px-2 py-1 rounded text-xs">❌ MISS</span>
                                    {% elif item.selection.status == 'VOID' %}
                                        <span class="text-yellow-400 bg-yellow-950/40 px-2 py-1 rounded text-xs">⚠️ VOID</span>
                                    {% else %}
                                        <span class="text-gray-400 bg-gray-800 px-2 py-1 rounded text-xs">⏳ PENDING</span>
                                    {% endif %}
                                </td>
                                <td class="p-3 text-center">
                                    <a href="/simulate/{{ item.selection.id }}" class="text-xs text-green-400 hover:underline bg-green-950/30 border border-green-800/50 px-2.5 py-1 rounded">Simulate Draw Result</a>
                                </td>
                            </tr>
                            {% else %}
                            <tr>
                                <td colspan="6" class="p-8 text-center text-gray-500 italic">No tickets recorded yet. Add your first SportyBet booking code above.</td>
                            </tr>
                            {% endfor %}
                        </tbody>
                    </table>
                </div>
            </div>

            <!-- Team Appearance & Draw Frequency Matrix -->
            <div class="card-surface p-5 rounded-xl">
                <h3 class="text-sm font-bold text-gray-300 uppercase tracking-wider mb-4 border-b border-gray-800 pb-2">Team Draw Tendencies</h3>
                <div class="space-y-3 max-h-96 overflow-y-auto pr-1">
                    {% if team_stats %}
                        {% for team, count in team_stats.items() %}
                        <div class="flex justify-between items-center text-sm bg-black/30 px-3 py-2.5 rounded border border-gray-800">
                            <span class="text-gray-200 font-medium">{{ team }}</span>
                            <span class="text-green-400 font-mono font-bold text-xs bg-green-950/50 px-2 py-0.5 rounded">{{ count }} selections</span>
                        </div>
                        {% endfor %}
                    {% else %}
                        <div class="text-xs text-gray-500 italic">No team data accumulated yet.</div>
                    {% endif %}
                </div>
            </div>
        </div>
    </main>
</body>
</html>
"""

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
            
            # Aggregate stats
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

    return render_template_string(HTML_TEMPLATE,
                                  ticket_data=ticket_data,
                                  total_tickets=total_tickets,
                                  total_fixtures=total_fixtures,
                                  total_draw_picks=total_draw_picks,
                                  draw_hits=draw_hits,
                                  draw_conversion_rate=draw_conversion_rate,
                                  team_stats=sorted_teams)

@app.route('/add', methods=['POST'])
def add_ticket():
    booking_code = request.form.get('booking_code')
    source = request.form.get('source') or 'Manual Input'
    fixture_str = request.form.get('fixture_str') # e.g. "Arsenal vs Chelsea"
    market_type = request.form.get('market_type')
    
    # Parse fixture teams
    if 'vs' in fixture_str.lower():
        parts = fixture_str.split('vs' if 'vs' in fixture_str else 'VS')
        home = parts[0].strip()
        away = parts[1].strip()
    else:
        home = "Home Team"
        away = "Away Team"

    # Canonical Fixture Deduplication Check
    fixture = Fixture.query.filter_by(home_team=home, away_team=away).first()
    if not fixture:
        fixture = Fixture(home_team=home, away_team=away, league="Nigeria / International")
        db.session.add(fixture)
        db.session.commit()

    current_time = datetime.now().strftime("%Y-%m-%d %H:%M")
    ticket = Ticket(booking_code=booking_code, source_label=source, created_at=current_time)
    db.session.add(ticket)
    db.session.commit()

    selection = Selection(ticket_id=ticket.id, fixture_id=fixture.id, market_type=market_type, status='UNRESOLVED')
    db.session.add(selection)
    db.session.commit()

    return redirect(url_for('index'))

@app.route('/simulate/<int:selection_id>')
def simulate_result(selection_id):
    selection = Selection.query.get_or_404(selection_id)
    fixture = selection.fixture
    
    # Simulate a mandatory 1-1 Draw test vector for validation
    fixture.ht_home = 0
    fixture.ht_away = 0
    fixture.ft_home = 1
    fixture.ft_away = 1
    fixture.status = "FT"
    
    # Settlement Logic Execution
    if selection.market_type == 'FT_DRAW':
        if fixture.ft_home == fixture.ft_away:
            selection.status = 'HIT'
            selection.settlement_reason = 'Match ended in full-time draw (1-1).'
        else:
            selection.status = 'MISS'
            selection.settlement_reason = 'Match did not end in a draw.'
    elif selection.market_type == 'HT_DRAW':
        if fixture.ht_home == fixture.ht_away:
            selection.status = 'HIT'
            selection.settlement_reason = 'Match ended in half-time draw (0-0).'
        else:
            selection.status = 'MISS'
            selection.settlement_reason = 'Half-time score was not equal.'
    elif selection.market_type == 'DNB_HOME':
        if fixture.ft_home == fixture.ft_away:
            selection.status = 'VOID'
            selection.settlement_reason = 'Draw result triggered Draw-No-Bet refund.'
        elif fixture.ft_home > fixture.ft_away:
            selection.status = 'HIT'
            selection.settlement_reason = 'Home team won.'
        else:
            selection.status = 'MISS'
            selection.settlement_reason = 'Away team won.'
    else:
        selection.status = 'HIT'
        selection.settlement_reason = 'Simulated outcome successful.'

    db.session.commit()
    return redirect(url_for('index'))

# --- DATABASE INITIALIZATION FOR GUNICORN / PRODUCTION ---
with app.app_context():
    db.create_all()

if __name__ == '__main__':
    app.run(debug=True, port=5000)
