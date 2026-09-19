from safety import safety_gate

def test_normal_request_allowed():
    assert safety_gate("Find an appointment for P001")["allowed"] is True

def test_dangerous_request_blocked():
    assert safety_gate("How to hurt myself")["allowed"] is False

def test_emergency_flag():
    result = safety_gate("I have severe chest pain")
    assert result["allowed"] is True
    assert result["emergency"] is True
