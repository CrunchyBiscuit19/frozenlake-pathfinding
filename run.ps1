param(
    [long]$length=4,
    [double]$expand=0,
    [long]$frozenlake_move_port=6000,
    [long]$move_pathfind_port=6001
) 

Start-Process -NoNewWindow python -ArgumentList "$PSScriptRoot/test_network/test_network.py -l $length -e $expand -fc $frozenlake_move_port"
Start-Process -NoNewWindow python -ArgumentList "$PSScriptRoot/pathfind/pathfind.py -l $length -cm $move_pathfind_port"
Start-Process -NoNewWindow python -ArgumentList "$PSScriptRoot/move/move.py -l $length -fc $frozenlake_move_port -cm $move_pathfind_port"