import os
import argparse
import random
import json
from multiprocessing.connection import Listener
import gym
from gym.envs.toy_text.frozen_lake import generate_random_map

CURRENT_DIR = os.path.abspath(os.path.dirname(__file__))

parser = argparse.ArgumentParser(description="Find edges (adjacent grid squares) in a FrozenLake OpenAI Gym environment.")
parser.add_argument("-l", metavar="--length", type=int, default=4, help="Length of the FrozenLake square map (default 4).")
parser.add_argument("-e", metavar="--expand", type=float, default=0, help="Value between 0 and 1 that randomly decides whether the FrozenLake map will be larger than specified by the length used. (default 0)")
parser.add_argument("-fc", metavar="--frozenlake-move", type=int, default=6000, help="Port number used to connect to the MOVE script socket (default 6000).")
args = parser.parse_args()
LENGTH = args.l
EXPAND_PROBABILITY = args.e
FROZENLAKE_MOVE_PORT = args.fc
FROZEN_ICE_PROBABILITY = 0.7
REWARD_SUCCESS = 1

# Scan current square and if surrounding squares exist on FrozenLake map
def scan_surroundings (random_map, current_position, current_actions):
    scan_results = {"current": None, 'u': False, 'd': False, 'l': False, 'r': False}
    directions_actions = {'u': 3, 'd': 1, 'l': 0, 'r': 2}
    test_env = gym.make("FrozenLake-v1", is_slippery=False, desc=random_map)
    # Check state of current square
    current_done, current_reward = False, 0
    test_env.reset()
    for current_action in current_actions:
        _, current_reward, current_done, _ = test_env.step(current_action)
    if (current_done and int(current_reward) == REWARD_SUCCESS): 
        scan_results["current"] = 'G'
    elif (current_done and int(current_reward) != REWARD_SUCCESS):
        scan_results["current"] = 'H'
    elif (not current_done):
        scan_results["current"] = 'F'
    # Test each direction
    for scan_direction, scan_action in directions_actions.items():
        test_env.reset()
        # Move to current position
        current_done = False
        for current_action in current_actions:
            _, _, current_done, _ = test_env.step(current_action)
        if current_done: # FrozenLake does not allow movement on H or G squares, so skip the scan
            scan_results.update({'u': None, 'd': None, 'l': None, 'r': None})
            break
        # Scan the surrounding squares
        test_observation, _, _, _ = test_env.step(scan_action)
        if test_observation == current_position:
            scan_results[scan_direction] = False
        else:
            scan_results[scan_direction] = True
    test_env.close()
    return scan_results

# Create random FrozenLake environments 
random_map = generate_random_map(size=LENGTH, p=FROZEN_ICE_PROBABILITY)
if (EXPAND_PROBABILITY > random.random()): # Chances of generating expanded map increases with increased EXPAND_PROBABILITY
    random_map = generate_random_map(size=LENGTH + 1, p=FROZEN_ICE_PROBABILITY)
env = gym.make("FrozenLake-v1", is_slippery=False, desc=random_map)

# Write FrozenLake map for review
with open(f"{CURRENT_DIR}/../results.json", 'w') as RESULTS_FILE:
    MAP_DATA = {"map": random_map}
    json.dump(MAP_DATA, RESULTS_FILE, indent=4)

# Socket connection with MOVE
listener = Listener(("localhost", FROZENLAKE_MOVE_PORT))
conn_move = listener.accept()

# Try every path suggested by MOVE
while True:
    # Stops if there are no more paths to try
    start_end = conn_move.recv()
    if (start_end == "end"):
        break
    
    # Reset for new path
    env.reset()
    # Keep requesting directions for current path until success or failure, then inform MOVE of success or failure
    current_actions = []
    while True:
        # Receive direction and step forward in path on FrozenLake
        action = conn_move.recv()
        observation, reward, done, info = env.step(action)
        current_actions.append(action)
        
        # Scan squares on, and around current position
        current_position = observation
        conn_move.recv() # MOVE requesting a scan
        scan_results = scan_surroundings(random_map, current_position, current_actions)            
        conn_move.send(scan_results)
        
        # Inform of continue, success or failure
        if done:
            conn_move.send("done")
            if (int(reward) == REWARD_SUCCESS):
                conn_move.send("success")
            else:
                conn_move.send("failure")
            break
        else:
            conn_move.send("not_done")

        # End of the path
        path_termination = conn_move.recv()
        if path_termination == "path_terminated":
            break

# End socket connection and close the FrozenLake environment
env.close()
listener.close()
conn_move.close()
