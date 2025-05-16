####################################################
# LSrouter.py
# Name:
# HUID:
#####################################################

import heapq
from json import dumps, loads

from packet import Packet
from router import Router


class LSrouter(Router):
    def __init__(self, addr, heartbeat_time):
        Router.__init__(self, addr)
        self.heartbeat_time = heartbeat_time
        self.last_time = 0
        self.addr = addr

        self.seq_num = 0
        self.topology = {addr: {}}  # addr -> {neighbor: cost}
        self.seq_nums = {}  # addr -> last seq_num seen
        self.eaddr = {}  # neighbor -> (cost, port)
        self.rtable = {}  # dest -> next_hop

    def handle_packet(self, port, packet):
        if packet.is_traceroute:
            dst = packet.dst_addr
            if dst in self.rtable:
                next_hop = self.rtable[dst]
                if next_hop in self.eaddr:
                    eport = self.eaddr[next_hop][1]
                    self.send(eport, packet)
        else:
            try:
                content = loads(packet.content)
                src = packet.src_addr
                seq = content["seq_num"]
                neighbors = content["neighbors"]

                if src not in self.seq_nums or seq > self.seq_nums[src]:
                    self.seq_nums[src] = seq
                    self.topology[src] = neighbors
                    self.update_routing_table()

                    for n, (_, p) in self.eaddr.items():
                        if n != src:
                            self.send(p, packet)

            except Exception as e:
                print(f"Error in handle_packet: {e}")

    def handle_new_link(self, port, endpoint, cost):
        self.eaddr[endpoint] = (cost, port)
        self.topology[self.addr][endpoint] = cost
        self.seq_num += 1
        self.broadcast_link_state()
        self.update_routing_table()

    def handle_remove_link(self, port):
        removed = None
        for n, (c, p) in self.eaddr.items():
            if p == port:
                removed = n
                break
        if removed:
            del self.eaddr[removed]
            if removed in self.topology[self.addr]:
                del self.topology[self.addr][removed]
            self.seq_num += 1
            self.broadcast_link_state()
            self.update_routing_table()

    def handle_time(self, time_ms):
        if time_ms - self.last_time >= self.heartbeat_time:
            self.last_time = time_ms
            self.seq_num += 1
            self.broadcast_link_state()

    def broadcast_link_state(self):
        content = {
            "seq_num": self.seq_num,
            "neighbors": self.topology[self.addr]
        }
        msg = dumps(content)
        for n, (_, port) in self.eaddr.items():
            packet = Packet(Packet.ROUTING, self.addr, n)
            packet.content = msg
            self.send(port, packet)

    def update_routing_table(self):
        dist = {self.addr: 0}
        prev = {}
        visited = set()
        heap = [(0, self.addr)]

        while heap:
            cost_u, u = heapq.heappop(heap)
            if u in visited:
                continue
            visited.add(u)

            for v in self.topology.get(u, {}):
                alt = cost_u + self.topology[u][v]
                if v not in dist or alt < dist[v]:
                    dist[v] = alt
                    prev[v] = u
                    heapq.heappush(heap, (alt, v))

        self.rtable.clear()
        for dest in dist:
            if dest == self.addr:
                continue
            # Tìm next hop
            hop = dest
            while prev[hop] != self.addr:
                hop = prev[hop]
            self.rtable[dest] = hop

    def __repr__(self):
        return f"LSrouter(addr={self.addr}, rtable={self.rtable})"
