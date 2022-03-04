#!/usr/bin/env bash

SCRIPT_DIR="$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"

length=$1
expand=$2
frozenlake_move_port=$3
move_pathfind_port=$4

if [[ -z $1 ]]
then
    length=4
fi
if [[ -z $2 ]]
then
    expand=0
fi
if [[ -z $3 ]]
then
    frozenlake_move_port=6000
fi
if [[ -z $4 ]]
then
    move_pathfind_port=6001
fi

python3 $SCRIPT_DIR/test_network/test_network.py -l $length -e $expand -fc $frozenlake_move_port &
python3 $SCRIPT_DIR/pathfind/pathfind.py -l $length -cm $move_pathfind_port &
python3 $SCRIPT_DIR/move/move.py -l $length -fc $frozenlake_move_port -cm $move_pathfind_port &