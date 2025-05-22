# Copyright (C) 2011 Nippon Telegraph and Telephone Corporation.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or
# implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
Two OpenFlow 1.0 L3 Static Routers and two OpenFlow 1.0 L2 learning switches.
"""


from ryu.base import app_manager
from ryu.controller import ofp_event
from ryu.controller.handler import MAIN_DISPATCHER
from ryu.controller.handler import set_ev_cls
from ryu.ofproto import ofproto_v1_0
from ryu.lib.mac import haddr_to_bin
from ryu.lib.packet import packet
from ryu.lib.packet import ethernet
from ryu.lib.packet import arp
from ryu.lib.packet import ipv4
from ryu.lib.packet import ether_types

# Router and host interface IPs and MACs for two routers
ROUTER1_LEFT_IP = "192.168.1.1"
ROUTER1_LEFT_MAC = "00:00:00:00:01:01"
ROUTER1_RIGHT_IP = "192.168.3.1"
ROUTER1_RIGHT_MAC = "00:00:00:00:03:01"
ROUTER2_LEFT_IP = "192.168.3.2"
ROUTER2_LEFT_MAC = "00:00:00:00:03:02"
ROUTER2_RIGHT_IP = "192.168.2.1"
ROUTER2_RIGHT_MAC = "00:00:00:00:02:01"
H1_IP = "192.168.1.2"
H1_MAC = "00:00:00:00:01:02"
H2_IP = "192.168.1.3"
H2_MAC = "00:00:00:00:01:03"
H3_IP = "192.168.2.2"
H3_MAC = "00:00:00:00:02:02"
H4_IP = "192.168.2.3"
H4_MAC = "00:00:00:00:02:03"

# Port to IP mapping for both routers (dpid 0x1A and 0x1B)
PORT_TO_IP = {
    0x1A: {1: ROUTER1_RIGHT_IP, 2: ROUTER1_LEFT_IP},  # port 1: inter-router, port 2: left subnet
    0x1B: {1: ROUTER2_LEFT_IP, 2: ROUTER2_RIGHT_IP}   # port 1: inter-router, port 2: right subnet
}

# Routing table for both routers (destination IP -> output port)
ROUTING_TABLE = {
    0x1A: {
        H1_IP: 2,  # left subnet
        H2_IP: 2,
        H3_IP: 1,  # right subnet via inter-router link
        H4_IP: 1,
        ROUTER2_LEFT_IP: 1,  # to right router
        ROUTER2_RIGHT_IP: 1
    },
    0x1B: {
        H3_IP: 2,  # right subnet
        H4_IP: 2,
        H1_IP: 1,  # left subnet via inter-router link
        H2_IP: 1,
        ROUTER1_LEFT_IP: 1,  # to left router
        ROUTER1_RIGHT_IP: 1
    }
}

# ARP table for both routers (IP -> MAC)
ARP_TABLE = {
    # Router 1
    ROUTER1_LEFT_IP: ROUTER1_LEFT_MAC,
    ROUTER1_RIGHT_IP: ROUTER1_RIGHT_MAC,
    H1_IP: H1_MAC,
    H2_IP: H2_MAC,
    # Router 2
    ROUTER2_LEFT_IP: ROUTER2_LEFT_MAC,
    ROUTER2_RIGHT_IP: ROUTER2_RIGHT_MAC,
    H3_IP: H3_MAC,
    H4_IP: H4_MAC
}

class SimpleSwitch(app_manager.RyuApp):
    OFP_VERSIONS = [ofproto_v1_0.OFP_VERSION]

    def __init__(self, *args, **kwargs):
        super(SimpleSwitch, self).__init__(*args, **kwargs)
        self.mac_to_port = {}

    def add_flow(self, datapath, match, actions):
        ofproto = datapath.ofproto

        mod = datapath.ofproto_parser.OFPFlowMod(
            datapath=datapath, match=match, cookie=0,
            command=ofproto.OFPFC_ADD, idle_timeout=0, hard_timeout=0,
            priority=ofproto.OFP_DEFAULT_PRIORITY,
            flags=ofproto.OFPFF_SEND_FLOW_REM, actions=actions)
        datapath.send_msg(mod)

    def modify_and_send_ip_packet(self, datapath, in_port, pkt, actions, out_port):
        # Extract IP and Ethernet headers from the packet
        ip_pkt = pkt.get_protocol(ipv4.ipv4)
        eth = pkt.get_protocol(ethernet.ethernet)
        self.logger.info("Forwarding packet: src_mac=%s dst_mac=%s src_ip=%s dst_ip=%s out_port=%d",
                         eth.src, eth.dst,
                         ip_pkt.src if ip_pkt else "N/A",
                         ip_pkt.dst if ip_pkt else "N/A",
                         out_port)
        out = datapath.ofproto_parser.OFPPacketOut(
            datapath=datapath,
            buffer_id=datapath.ofproto.OFP_NO_BUFFER,
            in_port=in_port,
            actions=actions,
            data=pkt.data
        )
        datapath.send_msg(out)

    @set_ev_cls(ofp_event.EventOFPPacketIn, MAIN_DISPATCHER)
    def _packet_in_handler(self, ev):
        msg = ev.msg
        datapath = msg.datapath
        dpid = datapath.id
        ofproto = datapath.ofproto

        pkt = packet.Packet(msg.data)
        eth = pkt.get_protocol(ethernet.ethernet)

        dst = eth.dst
        src = eth.src
        ethertype = eth.ethertype

        self.mac_to_port.setdefault(dpid, {})

        self.logger.info("packet in %s %s %s %s in_port=%s", hex(dpid).ljust(4), hex(ethertype), src, dst, msg.in_port)

        # learn a mac address to avoid FLOOD next time.
        self.mac_to_port[dpid][src] = msg.in_port

        if dpid == 0x1A:
            if ethertype == ether_types.ETH_TYPE_ARP: # this packet is ARP packet
                arp_pkt = pkt.get_protocol(arp.arp)
                if arp_pkt and arp_pkt.opcode == arp.ARP_REQUEST and arp_pkt.dst_ip in [ROUTER1_LEFT_IP, ROUTER1_RIGHT_IP, ROUTER2_LEFT_IP, ROUTER2_RIGHT_IP]:
                    self.arp_reply(datapath, eth, arp_pkt, arp_pkt.dst_ip, msg.in_port)
                return
            
            elif ethertype == ether_types.ETH_TYPE_IP: # this packet is IP packet
                ip_pkt = pkt.get_protocol(ipv4.ipv4)
                if ip_pkt and ip_pkt.dst in ROUTING_TABLE[dpid]:
                    out_port = ROUTING_TABLE[dpid][ip_pkt.dst]
                    router_mac = ARP_TABLE[PORT_TO_IP[dpid][out_port]]
                    if ip_pkt.dst in ARP_TABLE:
                        dst_mac = ARP_TABLE[ip_pkt.dst]
                        self.logger.info(f"[DPID {hex(dpid)}] out_port: {out_port}, router_mac: {router_mac}, dst_mac: {dst_mac}")
                        match = datapath.ofproto_parser.OFPMatch(
                            dl_type=ether_types.ETH_TYPE_IP,
                            nw_dst=ip_pkt.dst
                        )
                        actions = [
                            datapath.ofproto_parser.OFPActionSetDlSrc(router_mac),
                            datapath.ofproto_parser.OFPActionSetDlDst(dst_mac),
                            datapath.ofproto_parser.OFPActionOutput(out_port)
                        ]
                        self.modify_and_send_ip_packet(datapath, msg.in_port, pkt, actions, out_port)
                        self.add_flow(datapath, match, actions)
                    else:
                        self.logger.info(f"[DPID {hex(dpid)}] No ARP entry for {ip_pkt.dst}, skipping forwarding.")
                return
            return
        if dpid == 0x1B:
            if ethertype == ether_types.ETH_TYPE_ARP: # this packet is ARP packet
                arp_pkt = pkt.get_protocol(arp.arp)
                if arp_pkt and arp_pkt.opcode == arp.ARP_REQUEST and arp_pkt.dst_ip in [ROUTER1_LEFT_IP, ROUTER1_RIGHT_IP, ROUTER2_LEFT_IP, ROUTER2_RIGHT_IP]:
                    self.arp_reply(datapath, eth, arp_pkt, arp_pkt.dst_ip, msg.in_port)
                return
            elif ethertype == ether_types.ETH_TYPE_IP: # this packet is IP packet
                ip_pkt = pkt.get_protocol(ipv4.ipv4)
                if ip_pkt and ip_pkt.dst in ROUTING_TABLE[dpid]:
                    out_port = ROUTING_TABLE[dpid][ip_pkt.dst]
                    router_mac = ARP_TABLE[PORT_TO_IP[dpid][out_port]]
                    if ip_pkt.dst in ARP_TABLE:
                        dst_mac = ARP_TABLE[ip_pkt.dst]
                        self.logger.info(f"[DPID {hex(dpid)}] out_port: {out_port}, router_mac: {router_mac}, dst_mac: {dst_mac}")
                        match = datapath.ofproto_parser.OFPMatch(
                            dl_type=ether_types.ETH_TYPE_IP,
                            nw_dst=ip_pkt.dst
                        )
                        actions = [
                            datapath.ofproto_parser.OFPActionSetDlSrc(router_mac),
                            datapath.ofproto_parser.OFPActionSetDlDst(dst_mac),
                            datapath.ofproto_parser.OFPActionOutput(out_port)
                        ]
                        self.modify_and_send_ip_packet(datapath, msg.in_port, pkt, actions, out_port)
                        self.add_flow(datapath, match, actions)
                    else:
                        self.logger.info(f"[DPID {hex(dpid)}] No ARP entry for {ip_pkt.dst}, skipping forwarding.")
                return
            return
                 
        if dst in self.mac_to_port[dpid]:
            out_port = self.mac_to_port[dpid][dst]
        else:
            out_port = ofproto.OFPP_FLOOD

        match = datapath.ofproto_parser.OFPMatch(
            in_port=msg.in_port, dl_dst=haddr_to_bin(dst))

        actions = [datapath.ofproto_parser.OFPActionOutput(out_port)]

        # install a flow to avoid packet_in next time
        if out_port != ofproto.OFPP_FLOOD:
            self.add_flow(datapath, match, actions)

        data = None
        if msg.buffer_id == ofproto.OFP_NO_BUFFER:
            data = msg.data

        out = datapath.ofproto_parser.OFPPacketOut(
            datapath=datapath, buffer_id=msg.buffer_id, in_port=msg.in_port,
            actions=actions, data=data)
        datapath.send_msg(out)

    def arp_reply(self, datapath, eth, arp_pkt, target_ip, in_port):
        # Use the ARP_TABLE defined at the top
        target_mac = ARP_TABLE[target_ip]
        self.logger.info("Switch replying to ARP request for %s with MAC %s", target_ip, target_mac)
        arp_reply_pkt = packet.Packet()
        arp_reply_pkt.add_protocol(
            ethernet.ethernet(
                ethertype=ether_types.ETH_TYPE_ARP,
                dst=eth.src,
                src=target_mac
            )
        )
        arp_reply_pkt.add_protocol(
            arp.arp(
                opcode=arp.ARP_REPLY,
                src_mac=target_mac,
                src_ip=target_ip,
                dst_mac=eth.src,
                dst_ip=arp_pkt.src_ip
            )
        )
        arp_reply_pkt.serialize()
        actions = [datapath.ofproto_parser.OFPActionOutput(in_port)]
        out = datapath.ofproto_parser.OFPPacketOut(
            datapath=datapath,
            buffer_id=datapath.ofproto.OFP_NO_BUFFER,
            in_port=datapath.ofproto.OFPP_CONTROLLER,
            actions=actions,
            data=arp_reply_pkt.data
        )
        datapath.send_msg(out)

    @set_ev_cls(ofp_event.EventOFPPortStatus, MAIN_DISPATCHER)
    def _port_status_handler(self, ev):
        msg = ev.msg
        reason = msg.reason
        port_no = msg.desc.port_no

        ofproto = msg.datapath.ofproto
        if reason == ofproto.OFPPR_ADD:
            self.logger.info("port added %s", port_no)
        elif reason == ofproto.OFPPR_DELETE:
            self.logger.info("port deleted %s", port_no)
        elif reason == ofproto.OFPPR_MODIFY:
            self.logger.info("port modified %s", port_no)
        else:
            self.logger.info("Illeagal port state %s %s", port_no, reason)
