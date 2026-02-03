from flask import Blueprint, render_template

from app.strategies import get_all_strategies
from config import Config

main_bp = Blueprint("main", __name__)


@main_bp.route("/")
def index():
    strategies = get_all_strategies()
    return render_template(
        "index.html",
        strategies=strategies,
        instruments=Config.INSTRUMENTS,
        intervals=Config.INTERVALS,
        default_instrument=Config.DEFAULT_INSTRUMENT,
        default_interval=Config.DEFAULT_INTERVAL,
    )
