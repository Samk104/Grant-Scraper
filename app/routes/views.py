from threading import Thread
import traceback
from flask import Blueprint, render_template, request, jsonify, redirect, url_for, session, copy_current_request_context
from mib_app.services.scraper import get_recipe, get_prices_for_ingredient
from mib_app.services.utils import get_driver_pool, load_visited_urls, safe_write_results
import logging
import time
import json
import os
import random
from typing import Dict, List
from uuid import uuid4
from concurrent.futures import ThreadPoolExecutor, as_completed

main = Blueprint('main', __name__)

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

RESULTS_DIR = 'results'

if not os.path.exists(RESULTS_DIR):
    os.makedirs(RESULTS_DIR)

def get_session_id():
    if 'user_id' not in session:
        session['user_id'] = str(uuid4())
    return session['user_id']

def get_result_path():
    return os.path.join(RESULTS_DIR, f"results_{get_session_id()}.json")

@main.route('/')
def index():
    start = time.time()
    result = render_template("index.html")
    logger.info(f"Index route took {time.time() - start:.2f} seconds")
    return result

@main.route('/submit', methods=['POST'])
def submit():
    logger.info("Form submitted")

    session['dish'] = request.form.get('dish', '')
    session['zipcode'] = request.form.get('zipcode', '30324')

    result_path = get_result_path()
    if os.path.exists(result_path):
        os.remove(result_path)

    return redirect(url_for('main.loading'))

@main.route('/loading')
def loading():
    return render_template("loading.html")

@main.route('/check_results')
def check_results():
    session_id = get_session_id()
    result_path = get_result_path()
    lock_path = result_path.replace(".json", ".lock")

    dish = session.get('dish', '')
    zipcode = session.get('zipcode', '30324')

    if os.path.exists(result_path):
        with open(result_path, 'r') as f:
            results = json.load(f)
        progress = results.get('progress', {'total': 1, 'completed': 0})

        if progress['total'] == 1 and progress['completed'] == 0:
            return jsonify({'status': 'loading', 'progress': progress})

        status = 'ready' if progress['completed'] >= progress['total'] else 'loading'
        return jsonify({'status': status, 'results': results, 'progress': progress})

    if not dish:
        logger.error("No dish in session; skipping check_results")
        return jsonify({'status': 'waiting', 'message': 'No dish submitted yet'})

    if os.path.exists(lock_path):
        return jsonify({'status': 'loading', 'progress': {'total': 1, 'completed': 0}})

    with open(lock_path, 'w') as f:
        f.write("in_progress")


    @copy_current_request_context
    def background_scrape():
        try:
            logger.info("Calling get_recipe...")
            ingredients, image_url = get_recipe(dish)
            logger.info(f"get_recipe complete. Found {len(ingredients)} ingredients")

            if not ingredients:
                logger.warning("No ingredients found — aborting scrape")
                return

            visited_urls = load_visited_urls()
            stores = ['walmart', 'samsclub', 'kroger']
            net_store_cost = {}

            driver_pool = get_driver_pool()

            results = {
                'dish': dish,
                'ingredients': ingredients,
                'image_url': image_url,
                'net_store_cost': net_store_cost,
                'progress': {'total': len(ingredients), 'completed': 0}
            }

            with open(result_path, 'w') as f:
                safe_write_results(result_path, results)

            def process_ingredient(ingredient):

                local_driver = driver_pool.get_driver()
                if not local_driver:
                    return ingredient, False


                try:
                    logger.info(f"Started scraping for: {ingredient}")
                    for store in stores:
                        get_prices_for_ingredient(
                            ingredient,
                            [store],
                            zipcode,
                            net_store_cost,
                            visited_urls,
                            local_driver,
                            driver_pool
                        )
                        sleep_time = random.uniform(3.0, 5.0)
                        time.sleep(sleep_time)
                    return ingredient, True
                except Exception as e:
                    logger.error(f"Error processing {ingredient}: {e}")
                    return ingredient, False
                finally:
                    driver_pool.release_driver(local_driver)

            max_threads = min(4, len(ingredients))
            logger.info(f"Starting ThreadPoolExecutor with {max_threads} threads")

            with ThreadPoolExecutor(max_workers=max_threads) as executor:
                futures = {
                    executor.submit(process_ingredient, ing): ing for ing in ingredients
                }

                for future in as_completed(futures):
                    try:
                        ingredient, success = future.result()
                        logger.info(f"Future completed for: {ingredient}")
                    except Exception as e:
                        logger.error(f"Future failed: {e}")
                        continue

                    results['progress']['completed'] += 1
                    logger.info(f"Progress updated: {results['progress']['completed']}/{results['progress']['total']}")
                    with open(result_path, 'w') as f:
                        safe_write_results(result_path, results)
                    logger.info(f"{'✅' if success else '❌'} Done: {ingredient}")

            logger.info(f"Scraping complete for {dish}")

        except Exception as e:
            logger.error(f"Scrape failed: {e}")
            traceback.print_exc()
            try:
                results['error'] = str(e)
                with open(result_path, 'w') as f:
                    safe_write_results(result_path, results)
            except:
                pass

        finally:
            if os.path.exists(lock_path):
                os.remove(lock_path)
                logger.info(f"Lock file removed for session: {session_id}")

    Thread(target=background_scrape, name=f"Scraper-{session_id}").start()

    return jsonify({'status': 'loading', 'progress': {'total': 1, 'completed': 0}})

@main.route('/results')
def results():
    result_path = get_result_path()

    if not os.path.exists(result_path):
        return redirect(url_for('main.loading'))

    with open(result_path, 'r') as f:
        results = json.load(f)

    return render_template(
        "results.html",
        dish=results.get('dish', ''),
        ingredients=results.get('ingredients', []),
        image=results.get('image_url', ''),
        net_store_cost=results.get('net_store_cost', {}),
        length=len(results.get('ingredients', []))
    )

@main.route('/get-urls')
def get_urls():
    try:
        from mib_app.services.utils import load_visited_urls
        visited_dict = load_visited_urls()
        visited_list = list(visited_dict.keys())
        return jsonify(visited_list)
    except Exception as e:
        logger.error(f"Error in /get-urls: {e}")
        return jsonify([]), 500

@main.route('/error')
def error():
    return render_template("error.html")
