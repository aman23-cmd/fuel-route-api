"""
Cost-optimal refuelling plan.

Classic "gas station" problem, solved exactly with the greedy next-cheaper rule
(O(n)): at each station,
  * if a cheaper station (or the destination) is reachable on the fuel a full tank
    allows, buy only enough to get there;
  * otherwise fill the tank and drive to the cheapest station in range.
Fuel is bought only where it is cheapest, never more than needed.
"""
from dataclasses import dataclass


class NoFeasiblePlan(Exception):
    pass


@dataclass
class Node:
    pos: float          # miles along route used for the maths
    price: float        # $/gal (0 for destination)
    ref: object = None  # whatever the caller wants back (station index)
    shown_mile: float = None


@dataclass
class Stop:
    ref: object
    mile: float
    gallons: float
    price: float

    @property
    def cost(self):
        return self.gallons * self.price


def plan(nodes, total_miles, max_range, mpg):
    """
    nodes: stations along the route, sorted by pos. nodes[0] is the origin fill-up:
    the vehicle leaves the origin with an empty tank and buys its first fuel there.
    Returns a list[Stop] with gallons > 0.
    """
    tank = max_range / mpg
    end = Node(total_miles, 0.0)
    seq = list(nodes) + [end]
    n = len(seq)

    # next strictly-cheaper node for every node (monotonic stack)
    nxt, stack = [None] * n, []
    for i in range(n - 1, -1, -1):
        while stack and seq[stack[-1]].price >= seq[i].price:
            stack.pop()
        nxt[i] = stack[-1] if stack else None
        stack.append(i)

    eps = 1e-9
    stops, i, fuel = [], 0, 0.0
    while i < n - 1:
        cur = seq[i]
        j = nxt[i]
        if j is not None and seq[j].pos - cur.pos <= max_range + eps:
            need = (seq[j].pos - cur.pos) / mpg
            buy, target = max(0.0, need - fuel), j
        else:
            # fill up, then hop to the cheapest station within range
            window = [k for k in range(i + 1, n) if seq[k].pos - cur.pos <= max_range + eps]
            if not window:
                raise NoFeasiblePlan(
                    f"No station within {max_range:.0f} miles after mile {cur.pos:.0f}.")
            target = min(window, key=lambda k: (seq[k].price, -seq[k].pos))
            buy = tank - fuel
        if buy > eps:
            stops.append(Stop(cur.ref, cur.shown_mile if cur.shown_mile is not None else cur.pos,
                              buy, cur.price))
        fuel += buy - (seq[target].pos - cur.pos) / mpg
        i = target
    return stops
