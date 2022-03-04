connected(Pos1,Pos2) :- edge(Pos1,Pos2).
connected(Pos1,Pos2) :- edge(Pos2,Pos1).

path(Start,End,Complete_Path) :-
    travel(Start,End,[Start],Complete_Path).

% Straight path from start / penultimate to end if they are connected (base case).
travel(Start,End,Intermediate_Path,Complete_Path) :- 
    append(Intermediate_Path,[End],Complete_Path),
    connected(Start,End).

% Recursively stepping over middle nodes to get from start to end (recursive case).
travel(Start,End,Current_Visited,Path) :-
    connected(Start,Middle),   
    Middle \== End, % Keep going if the next node (Middle) is not the end.
    not(member(Middle,Current_Visited)), % Do not revisit the visited nodes (Visited).
    append(Current_Visited, [Middle], New_Visited), 
    travel(Middle,End,New_Visited,Path). 
    