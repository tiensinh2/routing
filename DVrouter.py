from json import dumps, loads

from packet import Packet
from router import Router


class DVrouter(Router):
    def __init__(self, addr, heartbeat_time):
        Router.__init__(self, addr)
        self.heartbeat_time = heartbeat_time
        self.last_time = 0
        self.infinity = 16
        self.addr = addr

        # Bảng định tuyến: {đích: (cost, next_hop, egress_port)}
        self.rtable = {addr: {"cost": 0, "nhop": addr, "eport": None}}

        # Thông tin neighbor: {port: neighbor_addr}
        self.nport = {}

        # Chi phí link: {neighbor_addr: (cost, egress_port)}
        self.eaddr = {}

    def handle_packet(self, port, packet):
        """Process incoming packet."""
        if packet.is_traceroute:  # Bỏ dấu ngoặc () vì đây là thuộc tính, không phải method
            # Xử lý gói dữ liệu traceroute
            if packet.dst_addr in self.rtable:
                entry = self.rtable[packet.dst_addr]
                if entry["cost"] < self.infinity and entry["eport"] is not None:
                    self.send(entry["eport"], packet)
        else:
            # Xử lý gói định tuyến
            try:
                neighbor_dv = loads(packet.content)
                neighbor_addr = packet.src_addr

                if neighbor_addr not in self.eaddr:
                    return

                neighbor_cost = self.eaddr[neighbor_addr]["cost"]
                changed = False

                for dest in neighbor_dv:
                    new_cost = neighbor_dv[dest]["cost"] + neighbor_cost
                    if new_cost > self.infinity:
                        new_cost = self.infinity

                    # Cập nhật route nếu tìm thấy đường đi tốt hơn
                    if dest not in self.rtable or new_cost < self.rtable[dest]["cost"]:
                        self.rtable[dest] = {
                            "cost": new_cost,
                            "nhop": neighbor_addr,
                            "eport": self.eaddr[neighbor_addr]["eport"]
                        }
                        changed = True
                    # Xử lý route poisoning
                    elif self.rtable[dest]["nhop"] == neighbor_addr:
                        if self.rtable[dest]["cost"] != new_cost:
                            self.rtable[dest]["cost"] = new_cost
                            if new_cost >= self.infinity:
                                self.rtable[dest]["nhop"] = None
                                self.rtable[dest]["eport"] = None
                            changed = True

                if changed:
                    self.broadcast_update()

            except Exception as e:
                print(f"Error processing routing packet: {e}")

    def handle_new_link(self, port, endpoint, cost):
        # Thêm thông tin link mới
        self.nport[port] = endpoint
        self.eaddr[endpoint] = {"eport": port, "cost": cost}

        # Thêm route trực tiếp đến neighbor
        if endpoint not in self.rtable or cost < self.rtable[endpoint]["cost"]:
            self.rtable[endpoint] = {
                "cost": cost,
                "nhop": endpoint,
                "eport": port
            }
            self.broadcast_update()

    def handle_remove_link(self, port):
        if port not in self.nport:
            return

        # Xóa thông tin link
        endpoint = self.nport[port]
        del self.nport[port]
        del self.eaddr[endpoint]

        # Đánh dấu các route đi qua link này là vô hạn
        changed = False
        for dest in list(self.rtable.keys()):
            if self.rtable[dest]["nhop"] == endpoint:
                self.rtable[dest] = {
                    "cost": self.infinity,
                    "nhop": None,
                    "eport": None
                }
                changed = True

        if changed:
            self.broadcast_update()

    def handle_time(self, time_ms):
        # Định kỳ gửi bảng định tuyến
        if time_ms - self.last_time >= self.heartbeat_time:
            self.last_time = time_ms
            self.broadcast_update()

    def broadcast_update(self):
        # Chuẩn bị bảng định tuyến đơn giản để gửi
        dv = {}
        for dest in self.rtable:
            dv[dest] = {
                "cost": self.rtable[dest]["cost"],
                "nhop": self.rtable[dest]["nhop"]
            }

        # Gửi đến tất cả neighbors
        for port in self.nport:
            neighbor = self.nport[port]
            packet = Packet(Packet.ROUTING, self.addr, neighbor)
            packet.content = dumps(dv)
            self.send(port, packet)

    def __repr__(self):
        return f"DVrouter(addr={self.addr}, rtable={self.rtable})"
