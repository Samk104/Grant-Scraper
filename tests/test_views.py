import os
import json
import sys
import types
import pytest
from flask import session
from mib_app import create_app
from unittest.mock import MagicMock

@pytest.fixture(autouse=True)
def mock_driver_pool(monkeypatch):
    dummy_driver_pool = MagicMock()
    dummy_driver_pool.get_driver.return_value = MagicMock()
    dummy_driver_pool.release_driver.return_value = None
    monkeypatch.setattr('mib_app.services.utils.get_driver_pool', lambda: dummy_driver_pool)


@pytest.fixture
def client():
    app = create_app()
    app.config['TESTING'] = True
    app.config['SECRET_KEY'] = 'testkey'

    with app.test_client() as client:
        with app.app_context():
            yield client

def test_index_route(client):
    res = client.get('/')
    assert res.status_code == 200
    assert b"Meal" in res.data or b"Budget" in res.data

def test_submit_route_sets_session(client):
    with client.session_transaction() as sess:
        sess.clear()

    res = client.post('/submit', data={'dish': 'cake', 'zipcode': '30324'}, follow_redirects=False)
    assert res.status_code == 302 
    assert '/loading' in res.headers['Location']

def test_loading_route(client):
    res = client.get('/loading')
    assert res.status_code == 200
    assert b"loading" in res.data.lower() or b"progress" in res.data.lower()

def test_check_results_no_dish(client):
    with client.session_transaction() as sess:
        sess.clear()

    res = client.get('/check_results')
    assert res.status_code == 200
    data = res.get_json()
    assert data['status'] == 'waiting'

def test_check_results_creates_lock_file(client):
    with client.session_transaction() as sess:
        sess['dish'] = 'pancake'
        sess['user_id'] = 'test-user-id'

    lock_path = f'results/results_test-user-id.lock'
    result_path = f'results/results_test-user-id.json'

    if os.path.exists(lock_path):
        os.remove(lock_path)
    if os.path.exists(result_path):
        os.remove(result_path)

    res = client.get('/check_results')
    assert res.status_code == 200
    data = res.get_json()
    assert data['status'] == 'loading'
    assert os.path.exists(lock_path)

    if os.path.exists(lock_path):
        os.remove(lock_path)

def test_results_route_redirects_if_missing_file(client):
    with client.session_transaction() as sess:
        sess['user_id'] = 'test-user-id'

    result_path = f'results/results_test-user-id.json'
    if os.path.exists(result_path):
        os.remove(result_path)

    res = client.get('/results')
    assert res.status_code == 302
    assert res.location.endswith('/loading')

def test_get_urls_returns_json(monkeypatch):
    
    dummy_urls = {"http://example.com": True, "https://food.com": True}

    
    fake_utils = types.SimpleNamespace()
    fake_utils.load_visited_urls = lambda: dummy_urls

    
    monkeypatch.setitem(sys.modules, 'mib_app.services.utils', fake_utils)

    from mib_app import create_app
    app = create_app()
    app.config['TESTING'] = True

    with app.test_client() as client:
        res = client.get('/get-urls')
        assert res.status_code == 200
        data = res.get_json()
        assert "http://example.com" in data
        assert "https://food.com" in data


def test_error_route(client):
    res = client.get('/error')
    assert res.status_code == 200
    assert b"error" in res.data.lower()
