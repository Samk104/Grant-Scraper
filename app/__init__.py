import os
from flask import Flask
from mib_app.routes.views import main
import atexit
from mib_app.services.utils import get_driver_pool

def create_app():
    app = Flask(__name__, template_folder='templates', static_folder='static')
    app.config['SECRET_KEY'] = os.urandom(24).hex()

    app.register_blueprint(main)
    def close_pool_if_initialized():
        try:
            pool = get_driver_pool()
            pool.close()
        except RuntimeError:
            pass  # Pool was never initialized

    atexit.register(close_pool_if_initialized)

    return app
