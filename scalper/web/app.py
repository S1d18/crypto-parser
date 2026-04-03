"""Flask + SocketIO web dashboard for the scalper bot."""

from flask import Flask, render_template, jsonify
from flask_socketio import SocketIO
from flask_cors import CORS

socketio = SocketIO()


def create_app(bot=None, storage=None):
    app = Flask(__name__)
    CORS(app)
    socketio.init_app(app, cors_allowed_origins="*")

    @app.route('/')
    def index():
        return render_template('index.html')

    @app.route('/api/status')
    def api_status():
        if bot:
            return jsonify(bot.get_status())
        return jsonify({'running': False, 'balance': 0})

    @app.route('/api/trades')
    def api_trades():
        if storage:
            return jsonify(storage.get_trade_history(100))
        return jsonify([])

    @app.route('/api/stats/daily')
    def api_daily_stats():
        if storage:
            return jsonify(storage.get_daily_stats())
        return jsonify({})

    @app.route('/api/stats/all')
    def api_all_stats():
        if storage:
            return jsonify(storage.get_all_stats())
        return jsonify({})

    @app.route('/api/equity')
    def api_equity():
        if storage:
            return jsonify(storage.get_equity_history())
        return jsonify([])

    if bot:
        def on_bot_event(event, data):
            socketio.emit(event, data)
        bot.on_update(on_bot_event)

    return app
