
import sys
import altair as alt

# Mock streamlit 
class MockSt:
    class session_state_class:
        def __init__(self):
            self.history = []
            self.latest = {}
            self.data_queue = None
            self.receiver = None

    session_state = session_state_class()
    
    def markdown(self, *args, **kwargs): pass
    def columns(self, *args): return [MockSt(), MockSt(), MockSt()]
    def warning(self, *args): pass
    def altair_chart(self, *args, **kwargs): 
        print("Chart created successfully")
    def __enter__(self): return self
    def __exit__(self, exc_type, exc_val, exc_tb): pass

sys.modules['streamlit'] = MockSt()

# Import the dashboard code (we need to be careful as it runs on import)
# Instead of importing, I'll copy the relevant logic I want to test
# specifically the data structure and altair chart creation

def test_logic():
    print("Testing data structure logic...")
    history = []
    
    # Simulate adding data
    item = {'room': 'room-1', 'temperature': 22.5, 'humidity': 45.0, 'timestamp': '12:00:00'}
    
    history.append({
        "Time": item['timestamp'],
        "Room": item['room'],
        "Temp": item['temperature'],
        "Hum": item['humidity']
    })
    
    # Simulate filtering
    room_id = 'room-1'
    room_data_list = [d for d in history if d['Room'] == room_id]
    
    assert len(room_data_list) == 1
    assert room_data_list[0]['Temp'] == 22.5
    print("Data filtering passed.")

    # Simulate chart creation
    print("Testing Altair chart creation...")
    base = alt.Chart(alt.Data(values=room_data_list)).encode(
        x=alt.X('Time:T', axis=alt.Axis(title=None, format='%H:%M:%S'))
    )

    line_temp = base.mark_line(color='orange').encode(
        y=alt.Y('Temp:Q', axis=alt.Axis(title='Temp (°C)', titleColor='orange'))
    )

    line_hum = base.mark_line(color='#5276A7').encode(
        y=alt.Y('Hum:Q', axis=alt.Axis(title='Hum (%)', titleColor='#5276A7'))
    )

    chart = alt.layer(line_temp, line_hum).resolve_scale(y='independent').properties(height=250)
    
    # Try to converting to dict to ensure it serializes without error
    chart.to_dict()
    print("Chart serialization passed.")

if __name__ == "__main__":
    test_logic()
