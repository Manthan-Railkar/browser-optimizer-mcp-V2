from app.diff.diff import difference_engine

def test_difference_engine_flow():
    url = "https://example.com/form"
    
    # 1. Initial State
    state_1 = [
        {"tag": "input", "id": "username", "name": "user", "text": "", "placeholder": "Enter username"},
        {"tag": "button", "id": "submit", "name": None, "text": "Submit", "placeholder": None}
    ]
    
    diff_1 = difference_engine.compute_diff(url, state_1)
    # First time, all elements are "added"
    assert len(diff_1["added"]) == 2
    assert len(diff_1["removed"]) == 0
    
    # 2. Add an element (Password input)
    state_2 = [
        {"tag": "input", "id": "username", "name": "user", "text": "", "placeholder": "Enter username"},
        {"tag": "input", "id": "password", "name": "pass", "text": "", "placeholder": "Enter password"},
        {"tag": "button", "id": "submit", "name": None, "text": "Submit", "placeholder": None}
    ]
    
    diff_2 = difference_engine.compute_diff(url, state_2)
    assert len(diff_2["added"]) == 1
    assert diff_2["added"][0]["id"] == "password"
    assert len(diff_2["removed"]) == 0
    
    # 3. Remove an element (Username input)
    state_3 = [
        {"tag": "input", "id": "password", "name": "pass", "text": "", "placeholder": "Enter password"},
        {"tag": "button", "id": "submit", "name": None, "text": "Submit", "placeholder": None}
    ]
    
    diff_3 = difference_engine.compute_diff(url, state_3)
    assert len(diff_3["added"]) == 0
    assert len(diff_3["removed"]) == 1
    assert diff_3["removed"][0]["id"] == "username"
    
    # Clean up
    difference_engine.clear_history(url)
    assert url not in difference_engine.history
