import sys
import os
import time

# Set up logging and add JARVIS dir to path if needed
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from agent import JarvisAgent

def run_tests():
    agent = JarvisAgent()
    print("Testing JARVIS agent offline...\n")
    
    test_inputs = [
        "what's the weather in Dharwad?",
        "what files are in my Downloads folder?",
        "set volume to 60",
        "take a screenshot",
        "remind me to drink water in 1 minute"
    ]
    
    for user_input in test_inputs:
        print(f"You: {user_input}")
        try:
            response = agent.process(user_input)
            print(f"JARVIS: {response}\n")
        except Exception as e:
            print(f"JARVIS CRASHED ON INPUT: {e}\n")
        
        # Avoid Groq rate limits
        time.sleep(3)

if __name__ == "__main__":
    run_tests()
