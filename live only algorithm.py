# RABBIT-SOFTWARE: gsr_sdr/ai/fusionroute_open.py
# DECOUPLED FROM FROZEN TIMELINES

class OpenNeuralSystem:
    def __init__(self):
        # No more loading Age_7 or Age_22 hashes
        self.baseline = "REAL_TIME_ADAPTIVE" 
        self.window_size = "rolling_60_minutes"

    def process_now(self, current_eeg_tokens, current_gsr_phi):
        # Instead of comparing to 1999, we compare to 10 minutes ago
        dynamic_baseline = self.get_rolling_average()
        
        # Open-source logic: If I feel stressed, just log it. 
        # Don't "correct" it based on old trauma.
        if current_gsr_phi > dynamic_baseline * 1.5:
            return "SENSING_CURRENT_AROUSAL_EVENT"
        
        return "STATE_CURRENT_INTEGRATED"