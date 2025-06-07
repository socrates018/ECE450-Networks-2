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
from ryu.lib.packet import vlan

# Router and host interface IPs and MACs
# Router 1: left (192.168.1.1, 00:00:00:00:01:01)
# Router 2: left (192.168.3.2, 00:00:00:00:03:02), right (192.168.2.1, 00:00:00:00:02:01)
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

ROUTING_TABLE = {
    0x1A: {
        H1_IP: 2,
        H2_IP: 2,
        H3_IP: 1,
        H4_IP: 1
    },
    0x1B: {
        H1_IP: 1,
        H2_IP: 1,
        H3_IP: 2,
        H4_IP: 2
    }
}

ARP_TABLE = {
    ROUTER1_LEFT_IP: ROUTER1_LEFT_MAC,
    ROUTER1_RIGHT_IP: ROUTER1_RIGHT_MAC,
    ROUTER2_LEFT_IP: ROUTER2_LEFT_MAC,
    ROUTER2_RIGHT_IP: ROUTER2_RIGHT_MAC,
    H1_IP: H1_MAC,
    H2_IP: H2_MAC,
    H3_IP: H3_MAC,
    H4_IP: H4_MAC
}

ROUTER1_SUBNET = "192.168.1.0"
ROUTER1_SUBNET_MASK = 24
ROUTER2_SUBNET = "192.168.2.0"
ROUTER2_SUBNET_MASK = 24

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
        self.logger.info("Modifying and sending IP packet")
        out = datapath.ofproto_parser.OFPPacketOut(
            datapath=datapath,
            buffer_id=datapath.ofproto.OFP_NO_BUFFER,
            in_port=in_port,
            actions=actions,
            data=pkt.data
        )
        datapath.send_msg(out)

    def L2_send(self, datapath, in_port, actions, msg=None):
        """Send a packet out with given actions (L2 forwarding), handling buffer_id/data logic."""
        ofproto = datapath.ofproto
        buffer_id = msg.buffer_id if msg else ofproto.OFP_NO_BUFFER
        if msg and buffer_id == ofproto.OFP_NO_BUFFER:
            data = msg.data
        else:
            data = None
        out = datapath.ofproto_parser.OFPPacketOut(
            datapath=datapath,
            buffer_id=buffer_id,
            in_port=in_port,
            actions=actions,
            data=data
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

        arp_pkt = pkt.get_protocol(arp.arp)
        ip_pkt = pkt.get_protocol(ipv4.ipv4)
        vlan_pkt = pkt.get_protocol(vlan.vlan)

        self.mac_to_port.setdefault(dpid, {})

        if dpid in (0x1A, 0x1B):
            self.logger.info("packet in %s %s %s %s in_port=%s", hex(dpid).ljust(4), hex(ethertype), src, dst, msg.in_port)

        # learn a mac address to avoid FLOOD next time.
        self.mac_to_port[dpid][src] = msg.in_port

        if dpid == 0x1A:
            if ethertype == ether_types.ETH_TYPE_ARP: 
                if arp_pkt.dst_ip == ROUTER1_LEFT_IP:
                    self.arp_reply(datapath, eth, arp_pkt, msg.in_port)
                return
            elif ethertype == ether_types.ETH_TYPE_IP:
                out_port = ROUTING_TABLE[dpid][ip_pkt.dst]

                # if out_port == ROUTING_TABLE[dpid][ip_pkt.src]:
                #     self.logger.info("[0x1A] Same subnet, drop")
                #     return

                if(out_port == 1):
                    router_mac = ROUTER1_RIGHT_MAC
                    dst_mac = ROUTER2_LEFT_MAC
                    match = datapath.ofproto_parser.OFPMatch(
                        dl_type=ether_types.ETH_TYPE_IP,
                        nw_dst=ROUTER2_SUBNET,
                        nw_dst_mask=ROUTER2_SUBNET_MASK
                    )
                else:
                    router_mac = ROUTER1_LEFT_MAC
                    dst_mac = ARP_TABLE[ip_pkt.dst]
                    match = datapath.ofproto_parser.OFPMatch(
                        dl_type=ether_types.ETH_TYPE_IP,
                        nw_dst=ip_pkt.dst
                    )

                self.logger.info(f"[DPID {hex(dpid)}] {msg.in_port} -> {out_port}, "
                                 f"{router_mac} -> {dst_mac}, "
                                 f"{ip_pkt.src} -> {ip_pkt.dst}")

                actions = [
                    datapath.ofproto_parser.OFPActionSetDlSrc(router_mac),
                    datapath.ofproto_parser.OFPActionSetDlDst(dst_mac),
                    datapath.ofproto_parser.OFPActionOutput(out_port)
                ]
                
                self.modify_and_send_ip_packet(datapath, msg.in_port, pkt, actions, out_port)
                self.add_flow(datapath, match, actions)
                return
        if dpid == 0x1B:
            if ethertype == ether_types.ETH_TYPE_ARP: 
                if arp_pkt.dst_ip == ROUTER2_RIGHT_IP:
                    self.arp_reply(datapath, eth, arp_pkt, msg.in_port)
                return
            elif ethertype == ether_types.ETH_TYPE_IP:
                out_port = ROUTING_TABLE[dpid][ip_pkt.dst]

                # if out_port == ROUTING_TABLE[dpid][ip_pkt.src]:
                #     self.logger.info("[0x1B] Same subnet, drop")
                #     return

                if(out_port == 1):
                    router_mac = ROUTER2_LEFT_MAC
                    dst_mac = ROUTER1_RIGHT_MAC
                    match = datapath.ofproto_parser.OFPMatch(
                        dl_type=ether_types.ETH_TYPE_IP,
                        nw_dst=ROUTER1_SUBNET,
                        nw_dst_mask=ROUTER1_SUBNET_MASK
                    )
                else:
                    router_mac = ROUTER2_RIGHT_MAC
                    dst_mac = ARP_TABLE[ip_pkt.dst]
                    match = datapath.ofproto_parser.OFPMatch(
                        dl_type=ether_types.ETH_TYPE_IP,
                        nw_dst=ip_pkt.dst
                    )

                self.logger.info(f"[DPID {hex(dpid)}] {msg.in_port} -> {out_port}, "
                                 f"{router_mac} -> {dst_mac}, "
                                 f"{ip_pkt.src} -> {ip_pkt.dst}")

                actions = [
                    datapath.ofproto_parser.OFPActionSetDlSrc(router_mac),
                    datapath.ofproto_parser.OFPActionSetDlDst(dst_mac),
                    datapath.ofproto_parser.OFPActionOutput(out_port)
                ]
                
                self.modify_and_send_ip_packet(datapath, msg.in_port, pkt, actions, out_port)
                self.add_flow(datapath, match, actions)
                return
        if dpid == 0x2:
            if msg.in_port == 4:
                match = datapath.ofproto_parser.OFPMatch(in_port=msg.in_port)
                actions = [datapath.ofproto_parser.OFPActionOutput(1),
                           datapath.ofproto_parser.OFPActionVlanid(200)]
            elif msg.in_port == 1:
                self.logger.info(f"[DPID {hex(dpid)}] Packet received on trunk port with VLANID {vlan_pkt.vid}")
                match = datapath.ofproto_parser.OFPMatch(in_port=msg.in_port, dl_vlan=vlan_pkt.vid)
                if vlan_pkt.vid == 200:
                    actions = [datapath.ofproto_parser.OFPActionOutput(4),
                           datapath.ofproto_parser.OFPActionStripVlan()]
                elif vlan_pkt.vid == 100:
                    match = datapath.ofproto_parser.OFPMatch(in_port=msg.in_port, dl_vlan=vlan_pkt.vid, dl_dst=haddr_to_bin(dst))
                    out_port = self.mac_to_port[dpid].get(dst)
                    if out_port == 2 or out_port == 3:
                        actions = [datapath.ofproto_parser.OFPActionOutput(out_port),
                                   datapath.ofproto_parser.OFPActionStripVlan()]
                    elif out_port is None:
                        actions = [
                            datapath.ofproto_parser.OFPActionOutput(2),
                            datapath.ofproto_parser.OFPActionOutput(3),
                            datapath.ofproto_parser.OFPActionStripVlan()
                        ]
            else: # msg.in_port is 2 or 3
                match = datapath.ofproto_parser.OFPMatch(in_port=msg.in_port, dl_dst=haddr_to_bin(dst))
                if dst in self.mac_to_port[dpid]:
                    out_port = self.mac_to_port[dpid][dst]
                else:
                    out_port = ofproto.OFPP_FLOOD
                
                actions_flood = [datapath.ofproto_parser.OFPActionOutput(ofproto.OFPP_FLOOD)]

                actions = [datapath.ofproto_parser.OFPActionOutput(out_port)]

                actions_trunk= [datapath.ofproto_parser.OFPActionOutput(out_port),
                               datapath.ofproto_parser.OFPActionVlanid(100)]
                
                if out_port == ofproto.OFPP_FLOOD:
                    self.L2_send(datapath, msg.in_port, actions, msg.data)
                elif out_port == 4:
                    return
                elif out_port == 1:
                    self.add_flow(datapath, match, actions_trunk)
                else:
                    self.add_flow(datapath, match, actions)

                if

            data = None
            if msg.buffer_id == ofproto.OFP_NO_BUFFER:
                data = msg.data

            out = datapath.ofproto_parser.OFPPacketOut(
                datapath=datapath, buffer_id=msg.buffer_id, in_port=msg.in_port,
                actions=actions, data=data)
            datapath.send_msg(out)
            self.add_flow(datapath, match, actions)
            return
        
        if dpid == 0x3:
            # Future implementation for dpid 0x3
            return
        
        self.logger.info(f"[DPID {hex(dpid)}] {msg.in_port} -> {out_port}, "
                        f"{src} -> {dst}, VLANID {vlan_pkt.vid if vlan_pkt else 'None'}")
                 
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

    def arp_reply(self, datapath, eth, arp_pkt, in_port):
        if arp_pkt.opcode is not arp.ARP_REQUEST:
            self.logger.info("Received non-ARP request packet: %s", arp_pkt)
            return
        target_ip = arp_pkt.dst_ip
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
            self.logger.info("Illegal port state %s %s", port_no, reason)
