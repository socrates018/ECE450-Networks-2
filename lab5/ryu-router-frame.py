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
An OpenFlow 1.0 L3 Static Router and two OpenFlow 1.0 L2 learning switches.
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
from ryu.lib.packet import arp
from ryu.lib.packet import icmp

# Define variables for router and host interface IPs and MACs
ROUTER_IP1 = "192.168.1.1"
ROUTER_IP2 = "192.168.2.1"
ROUTER_MAC1 = "00:00:00:00:01:01"
ROUTER_MAC2 = "00:00:00:00:02:01"
H1_IP = "192.168.1.2"
H1_MAC = "00:00:00:00:01:02"
H2_IP = "192.168.1.3"
H2_MAC = "00:00:00:00:01:03"
H3_IP = "192.168.2.2"
H3_MAC = "00:00:00:00:02:02"
H4_IP = "192.168.2.3"
H4_MAC = "00:00:00:00:02:03"

PORT_TO_IP = {
    1: ROUTER_IP1,
    2: ROUTER_IP2
}


ROUTING_TABLE = {
    H1_IP: 1,
    H2_IP: 1,
    H3_IP: 2,
    H4_IP: 2
}


ARP_TABLE = {
    ROUTER_IP1: ROUTER_MAC1,
    ROUTER_IP2: ROUTER_MAC2,
    H1_IP: H1_MAC,
    H2_IP: H2_MAC,
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

        #arp proto info
        arp_pkt = pkt.get_protocol(arp.arp)

        #ipv4 proto info
        ip_pkt = pkt.get_protocol(ipv4.ipv4)
        # parser = datapath.ofproto_parser

        self.mac_to_port.setdefault(dpid, {})

        # self.logger.info("packet in %s %s %s %s in_port=%s", hex(dpid), hex(ethertype), src, dst, msg.in_port)
        if dpid == 1 and not dst.lower().startswith('33:33'):
            self.logger.info(
                "PacketIn: dpid=%s, ethertype=0x%04x, src_mac=%s, dst_mac=%s, in_port=%s",
                hex(dpid), ethertype, src, dst, msg.in_port
            )

        # learn a mac address to avoid FLOOD next time.
        self.mac_to_port[dpid][src] = msg.in_port

        if dpid == 1:
            if eth.ethertype == ether_types.ETH_TYPE_ARP: # this packet is ARP packet
                self.logger.info("Received ARP packet: %s", arp_pkt)
                if arp_pkt and arp_pkt.opcode == arp.ARP_REQUEST:
                    target_ip = arp_pkt.dst_ip
                    self.logger.info("ARP request for %s from %s", target_ip, arp_pkt.src_ip)
                    # Only reply if the ARP request is for one of the router's IPs
                    if target_ip == ROUTER_IP1 or target_ip == ROUTER_IP2:
                        self.logger.info("Preparing ARP reply for %s", target_ip)
                        self.arp_reply(datapath, eth, arp_pkt, target_ip, msg.in_port)
                return
            elif eth.ethertype == ether_types.ETH_TYPE_IP:
                if ip_pkt.proto == 1:
                    self.logger.info("Received ICMP packet: src=%s, dst=%s", ip_pkt.src, ip_pkt.dst)
                self.logger.info("Received IP packet: %s", ip_pkt)
                if ip_pkt and ip_pkt.dst in ARP_TABLE:

                    self.logger.info("Handling IP packet from %s to %s", ip_pkt.src, ip_pkt.dst)
                    # self.modify_and_send_ip_packet(datapath, msg.in_port, pkt)

                    # Add flow after forwarding the packet
                    out_port = ROUTING_TABLE[ip_pkt.dst]
                    router_mac = ARP_TABLE[PORT_TO_IP[out_port]]
                    dst_mac = ARP_TABLE[ip_pkt.dst]
                    self.logger.info("Setting actions: set_dl_src=%s, set_dl_dst=%s, output=%d", router_mac, dst_mac, out_port)
                    match = datapath.ofproto_parser.OFPMatch(
                        dl_type=ether_types.ETH_TYPE_IP,
                        nw_dst=ip_pkt.dst
                    )
                    actions = [
                        datapath.ofproto_parser.OFPActionSetDlSrc(router_mac),
                        datapath.ofproto_parser.OFPActionSetDlDst(dst_mac),
                        datapath.ofproto_parser.OFPActionOutput(out_port)
                    ]
                    self.add_flow(datapath, match, actions)
                    self.logger.info("Flow installed for IP dst %s out port %d", ip_pkt.dst, out_port)
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

    """
    fill in the code here for the ARP reply functions.
    """
        
    # def modify_and_send_ip_packet(self, datapath, in_port, pkt):
    #     # Extract IP and Ethernet headers from the packet
    #     ip_pkt = pkt.get_protocol(ipv4.ipv4)
    #     eth = pkt.get_protocol(ethernet.ethernet)
    #     dst_ip = ip_pkt.dst
    #
    #     out_port = ROUTING_TABLE[dst_ip]
    #
    #     self.logger.info("Routing IP packet to %s via port %d", dst_ip, out_port)
    #
    #     # Modify the IP packet's destination and source MAC address
    #     eth.src = ARP_TABLE[PORT_TO_IP[out_port]]
    #     eth.dst = ARP_TABLE[dst_ip]
    #     pkt.serialize()
    #     # Print packet info before sending
    #     self.logger.info("Forwarding packet: src_mac=%s dst_mac=%s src_ip=%s dst_ip=%s out_port=%d",
    #                      eth.src, eth.dst,
    #                      ip_pkt.src if ip_pkt else "N/A",
    #                      ip_pkt.dst if ip_pkt else "N/A",
    #                      out_port)
    #     actions = [datapath.ofproto_parser.OFPActionOutput(out_port)]
    #     out = datapath.ofproto_parser.OFPPacketOut(
    #         datapath=datapath,
    #         buffer_id=datapath.ofproto.OFP_NO_BUFFER,
    #         in_port=in_port,
    #         actions=actions,
    #         data=pkt.data
    #     )
    #     datapath.send_msg(out)

    def arp_reply(self, datapath, eth, arp_pkt, target_ip, in_port):
        self.logger.info("Building ARP reply for %s -> %s", target_ip, arp_pkt.src_ip)
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
        self.logger.info("Sending ARP reply out port %d", in_port)
        match = datapath.ofproto_parser.OFPMatch(
            dl_type=ether_types.ETH_TYPE_ARP,
            nw_dst=arp_pkt.src_ip,
            nw_proto=arp.ARP_REPLY  # Match ARP reply opcode for spoofing defense
            # You can add more fields here for stricter matching if needed
        )
        self.add_flow(datapath, match, actions)

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
