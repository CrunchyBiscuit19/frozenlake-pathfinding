import os
import argparse
import json
from multiprocessing.connection import Client, Listener

CURRENT_DIR = os.path.abspath(os.path.dirname(__file__))

parser = argparse.ArgumentParser(description="Sends FrozenLake directions to traverse within the FrozenLake map, and communicate with PathFind to recalculate paths when new squares are discovered on FrozenLake.")
parser.add_argument("-l", metavar="--length", type=int, default=4, help="Length of the FrozenLake square map (default 4).")
parser.add_argument("-fc", metavar="--frozenlake-move", type=int, default=6000, help="Port number used to connect to the FrozenLake script socket (default 6000).")
parser.add_argument("-cm", metavar="--move-PathFind", type=int, default=6001, help="Port number used to connect to the PathFind script socket (default 6001).")
args = parser.parse_args()
LENGTH = args.l
FROZENLAKE_MOVE_PORT = args.fc
MOVE_PathFind_PORT = args.cm

# Class for coordinates
class Point:
    def __init__(self, x, y):
        self.x = x
        self.y = y

    def get(self):
        return (self.x,self.y)

    # Makes it easy working with other coordinates
    def __add__(self, other_point):
        return Point(self.x + other_point.x, self.y + other_point.y)
    def __sub__(self, other_point):
        return Point(self.x - other_point.x, self.y - other_point.y)

    # For hashing (dictionary keys) and comparisons
    def __hash__(self):
        return hash((self.x, self.y))
    def __eq__(self, other_point):
        return (self.x, self.y) == (other_point.x, other_point.y)
    def __ne__(self, other_point):
        return not (self == other_point)

# Class for paths that come through from PathFind
class Path:
    def __init__(self, index, steps):
        self.index = index
        self.steps = steps
        self.directions = []
        self.actions = []
        self.current_coordinates = Point(0, 0)

    # Get directions in between each steps of the path
    def steps_to_direction (self):
        changes_directions_mapping = {Point(0, -1): 'u', Point(0, 1): 'd', Point(-1, 0): 'l', Point(1, 0):'r'}
        for i in range(len(self.steps) - 1):
            current_step = Point(*self.steps[i])
            next_step = Point(*self.steps[i + 1])
            change = next_step - current_step
            direction = changes_directions_mapping[change]
            self.directions.append(direction)

    # Convert path's directions into actions
    def directions_to_actions (self):
        directions_actions_mapping = {'u': 3, 'd': 1, 'l': 0, 'r': 2}
        for direction in self.directions:
            action = directions_actions_mapping[direction]
            self.actions.append(action)

    # Update the current coordinates of the path as it is being traversed
    def update_coordinates (self, direction):
        directions_changes_mapping = {'u': (0, -1), 'd': (0, 1), 'l': (-1, 0), 'r': (1, 0)}
        self.current_coordinates += Point(*directions_changes_mapping[direction])

# Connect to PathFind to communicate about paths and FrozenLake's map
listener = Listener(("localhost", MOVE_PathFind_PORT))
conn_PathFind = listener.accept()

# Connect socket to FrozenLake script to feed directions
conn_frozenlake = Client(("localhost", FROZENLAKE_MOVE_PORT))

# Constantly communicate with PathFind, to test Paths from PathFind and tell it when to recalculate
while True:
    # Get told by PathFind when to stop
    start_end = conn_PathFind.recv()
    if start_end == "end":
        break

    # Get paths to test from PathFind
    tried_paths = {"success": [], "failure": []}
    paths_steps = conn_PathFind.recv()

    # Feed the directions of every path to FrozenLake
    for i, path_steps in enumerate(paths_steps):
        conn_frozenlake.send("start")
        
        # Initialize current path and get details
        path = Path(i, path_steps)
        path.steps_to_direction()
        path.directions_to_actions()
        
        # Send actions to PT network script one by one
        for k, (action, direction) in enumerate(zip(path.actions, path.directions)):
            conn_frozenlake.send(action)
            path.update_coordinates(direction)

            # Scan after each action
            conn_frozenlake.send("scan_start")
            scan_results = conn_frozenlake.recv()
            scan_results.update({"coordinates": path.current_coordinates.get()})
            conn_PathFind.send("more_scans")
            conn_PathFind.send(scan_results)

            # Check success or failure
            is_done = conn_frozenlake.recv()
            if (is_done == "done"):
                status = conn_frozenlake.recv()
                if (status == "success"):
                    tried_paths["success"].append({"index": path.index, "steps": path.steps, "directions": path.directions})
                else:
                    tried_paths["failure"].append({"index": path.index, "steps": path.steps, "directions": path.directions})                
                break
            
            # If it does not reach the goal, assume failure
            if (k != len(path.actions) - 1):
                conn_frozenlake.send("path_not_terminated")
            else:
                tried_paths["failure"].append({"index": path.index, "steps": path.steps, "directions": path.directions})
                conn_frozenlake.send("path_terminated")

    # Stop PathFind from updating its internal map
    conn_PathFind.send("no_more_scans")

# End socket connection in MOVE, PathFind, and test network scripts
conn_frozenlake.send("end")
conn_frozenlake.close()
listener.close()
conn_PathFind.close()
     
# Write all the data about the paths into a JSON file
RESULTS_DATA = {}
with open(f"{CURRENT_DIR}/../results.json") as RESULTS_FILE:
    RESULTS_DATA = json.load(RESULTS_FILE)
with open(f"{CURRENT_DIR}/../results.json", 'w') as RESULTS_FILE:
    RESULTS_DATA.update({
        "successful_paths": tried_paths["success"],
        "successful_count": len(tried_paths["success"]),
    })
    json.dump(RESULTS_DATA, RESULTS_FILE, indent=4)