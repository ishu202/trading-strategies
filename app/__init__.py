import logging
from flask import Flask
from config import Config

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)


def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    from app.routes.main import main_bp
    from app.routes.api import api_bp

    app.register_blueprint(main_bp)
    app.register_blueprint(api_bp, url_prefix="/api")

    return app
