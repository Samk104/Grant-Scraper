import os

def create_app():

    # app.config['SECRET_KEY'] = os.urandom(24).hex()

    # app.register_blueprint(main)
    # def close_pool_if_initialized():
    #     try:
    #         pool = get_driver_pool()
    #         pool.close()
    #     except RuntimeError:
    #         pass  # Pool was never initialized

    # atexit.register(close_pool_if_initialized)

    return None
