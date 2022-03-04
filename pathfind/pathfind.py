import os
import re
import argparse
import numpy as np
import networkx as nx
from pyswip import Prolog
from multiprocessing.connection import Client

CURRENT_DIR = os.path.abspath(os.path.dirname(__file__))

parser = argparse.ArgumentParser(description="Calculates paths in a FrozenLake map from start to goal.")
parser.add_argument("-l", metavar="--length", type=int, default=4, help="Length of the FrozenLake square map (default 4).")
parser.add_argument("-cm", metavar="--move-pathfind", type=int, default=6001, help="Port number used to connect to the MOVE script socket (default 6001).")
args = parser.parse_args()
LENGTH = args.l
MOVE_MULVAL_PORT = args.cm

# Class for PathFind's internal map of FrozenLake
class Map ():
    def __init__(self, length=LENGTH):
        self.length = length
        self.map_grid = None
        self.target = (0,0)
        self.goal_found = False

    # Initialize empty map for PathFind to keep track of FrozenLake
    def initialize_map (self):
        map_grid = np.empty([self.length, self.length], dtype=str)
        # Fill with S and X
        for y, x in np.ndindex(map_grid.shape):
            map_grid[y, x] = 'X'
            if y == 0 and x == 0:
                map_grid[y, x] = 'S'
        map_grid = np.array(map_grid, dtype="str")
        self.map_grid = map_grid
        # S: Start
        # F: Frozen Ice
        # H: Hole
        # G: Goal
        # X: Unknown
        # I: Ignore
        # O: Filler
        # Z: Unreachable

    # Get map as Numpy array
    def get_map (self):
        return self.map_grid

    # Expand the map with additional rows and columns when needed
    def expand_map (self, new_coordinates):
        new_x, new_y = new_coordinates
        current_y, current_x = tuple(i - 1 for i in self.map_grid.shape)
        expansion = [[0,0],[0,0]] # Directions of columns / rows to add (up down left right)
        if new_x < 0:
            expansion[1][0] = abs(new_x)
        if new_x > current_x:
            expansion[1][1] = new_x - current_x 
        if new_y < 0:
            expansion[0][0] = abs(new_y)
        if new_y > current_y:
            expansion[0][1] = new_y - current_y 
        # Add columns accordingly
        self.map_grid = np.pad(self.map_grid, expansion, constant_values='O')
        
    # Update the map with X tiles as they are scanned
    def update_map (self, current_tile, coordinates, surroundings):
        x, y = coordinates
        new_x, new_y =  x, y
        # Update current tile in the map
        previous_tile = self.map_grid[y, x]
        self.map_grid[y, x] = current_tile
        if (previous_tile != current_tile):
            print(f"\nTile [{x}, {y}] updated")
            print(self.get_map())
        # Check if each direction has revealed new unexplored (X) areas
        for direction, available in surroundings.items():
            # True for surrounded by other squares, False for not, None for don't know (H and G prevents movement)
            if not available: 
                continue
            if direction == 'O':
                new_x, new_y = x, y - 1
            if direction == 'd':
                new_x, new_y = x, y + 1
            if direction == 'l':
                new_x, new_y = x - 1, y
            if direction == 'r':
                new_x, new_y = x + 1, y
            # Do not replace with X is it's S, F, G, or H
            try:    
                if self.map_grid[new_y, new_x] in ['S', 'F', 'G', 'H']:
                    continue
            except IndexError:
                pass        
            # Update the map with extra X, expand if needed
            try:
                self.map_grid[new_y, new_x] = 'X'
            except IndexError:
                self.expand_map((new_x, new_y))
                self.map_grid[new_y, new_x] = 'X'

    # Sets a target for PathFind's pathfinding
    def update_target (self):
        # Set each unexplored node to pathfind to, to scan the entire map
        unexplored = np.where(self.map_grid == 'X')
        if len(unexplored[0]) > 0:
            unexplored_coordinates = (unexplored[1][0], unexplored[0][0])
            # If same unexplored node is tried twice, list as ignored 
            if self.target == unexplored_coordinates:
                self.map_grid[unexplored_coordinates[1], unexplored_coordinates[0]] = 'I'
            else:
                self.target = unexplored_coordinates
            return
        # Once there are no more unexplored areas, try previously ignored areas 
        ignored = np.where(self.map_grid == 'I')
        if len(ignored[0]) > 0:
            ignored_coordinates = (ignored[1][0], ignored[0][0])
            # If same ignored node is tried twice, it is unreachable
            if self.target == ignored_coordinates:
                self.map_grid[ignored_coordinates[1], ignored_coordinates[0]] = 'Z'
            else:
                self.target = ignored_coordinates
            return
        # Assign goal as target once the map is fully explored
        goal = np.where(self.map_grid == 'G')
        if len(goal[0]) > 0:
            self.target = (goal[0][0], goal[1][0])
            self.goal_found = True

    # Convert grid map into edges of node graph representation
    def find_edges (self):
        map_graph = nx.Graph()
        for y, x in np.ndindex(self.map_grid.shape):
            # Add node of tile in map grid
            map_tile = self.map_grid[y, x]
            map_graph.add_node((x, y, map_tile))
            
            # H nodes are ignored
            if map_tile in ['H', 'O']:
                continue

            # Add edges (H or O not should be connected via edges)
            # Avoid negative index and index errors as well
            try:
                if x > 0:
                    left_map_item = self.map_grid[y, x - 1]
                    if left_map_item not in ['H', 'O']:
                        map_graph.add_edge((x - 1, y), (x, y))
            except IndexError:
                pass
            try:
                if y > 0:
                    up_map_item = self.map_grid[y - 1, x]
                    if up_map_item not in ['H', 'O']:
                        map_graph.add_edge((x, y - 1), (x, y))
            except IndexError:
                pass

        # Open and write into Prolog file
        map_edges = list(map_graph.edges())
        with open(f"{CURRENT_DIR}/edges.pl", 'w') as edges_file:
            for edge in map_edges:
                edges_file.write(f"edge({edge[0]},{edge[1]}).\n")

    # Prolog query to get all paths it can find from the connected nodes
    def get_paths (self):
        self.find_edges()

        # Use Prolog script to calculate and query paths
        prolog = Prolog()
        prolog.consult("{}/edges.pl".format(CURRENT_DIR.replace('\\', '/'))) # Windows backslash is seen as syntax error when path is converted into binary string during query 
        prolog.consult("{}/paths.pl".format(CURRENT_DIR.replace('\\', '/'))) # str.format because F-string does not support backslashes
        results = list(prolog.query(f"findall(Path, path((0, 0), {str(self.target)}, Path), Paths)."))[0]["Paths"]  
        
        # Converting the results into tuples in lists format
        paths = []
        for result in results:
            path = []
            for coordinates in result:
                coordinates = coordinates.value[1:]
                coordinates_regex = "\((\d+), (\d+)\)"
                coordinates_x = int(re.search(coordinates_regex, coordinates).group(1))
                coordinates_y = int(re.search(coordinates_regex, coordinates).group(2))
                path.append((coordinates_x, coordinates_y))
            paths.append(path)
        return paths

# Create an internal map to track movement on FrozenLake
map = Map(LENGTH)
map.initialize_map()

# Setup socket connection with MOVE
conn_move = Client(("localhost", MOVE_MULVAL_PORT))

# Cycle of MOVE testing each step of path, while PathFind either updates its internal map or calculates new paths
while True:
    # Tells MOVE when to start
    conn_move.send("start")

    # Update target as X to get paths to scan entire map, or as G to  
    # Send the paths to MOVE
    map.update_target()
    paths_steps = map.get_paths()
    conn_move.send(paths_steps)

    # Get scan results from MOVE after taking a step in the current paths
    while True:
        # Check if there are more scans coming in from paths
        scans_left = conn_move.recv()
        if scans_left == "no_more_scans":
            break
        # Update internal map using scan results
        scan_results = conn_move.recv()
        x, y = scan_results["coordinates"]
        current_tile = scan_results["current"]
        surroundings = scan_results
        del surroundings["coordinates"]
        del surroundings["current"]
        map.update_map(current_tile, (x, y), surroundings)

    # Can stop after testing paths leading to the goal
    if map.goal_found:
        break

conn_move.send("end")
conn_move.close()

print("\nPathfinding over.")