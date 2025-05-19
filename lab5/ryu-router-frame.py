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


"""
fill in the code here for any used constant (optional).


"""

def ip_to_port(ip):
    if ip == '192.168.1.1': return 1
    if ip == '192.168.2.1': return 2

def modify_and_send_packet(datapath, in_port, packet_data, ip_to_port, switch_mac):
    """
    Modifies Ethernet headers of received IP packet and sends it out
    Args:
        datapath: Switch datapath object
        in_port: Input port number
        packet_data: Original packet data (bytes)
        ip_to_port: Dictionary mapping IPs to output ports
        switch_mac: MAC address to use as source
    """
    from ryu.lib.packet import packet, ethernet, ipv4
    from ryu.ofproto import ofproto_v1_3
    
    # Parse original packet
    pkt = packet.Packet(packet_data)
    eth_original = pkt.get_protocol(ethernet.ethernet)
    ip_pkt = pkt.get_protocol(ipv4.ipv4)

    # Only process IP packets
    if not ip_pkt:
        return

    # Create new packet with modified Ethernet headers
    new_pkt = packet.Packet()
    
    # Set new Ethernet headers (preserve dst MAC and ethertype)
    new_eth = ethernet.ethernet(
        dst=eth_original.dst,
        src=switch_mac,
        ethertype=eth_original.ethertype
    )
    new_pkt.add_protocol(new_eth)

    # Copy all other protocols (IP, transport, payload)
    for proto in pkt.protocols[1:]:  # Skip original Ethernet
        new_pkt.add_protocol(proto)

    # Serialize the new packet
    new_pkt.serialize()

    # Get output port from mapping or flood
    ofproto = datapath.ofproto
    out_port = ip_to_port.get(ip_pkt.dst, ofproto.OFPP_FLOOD)

    # Send modified packet
    parser = datapath.ofproto_parser
    actions = [parser.OFPActionOutput(out_port)]
    out = parser.OFPPacketOut(
        datapath=datapath,
        buffer_id=ofproto.OFP_NO_BUFFER,
        in_port=in_port,
        actions=actions,
        data=new_pkt.data)
    datapath.send_msg(out)



def arp_reply(self, datapath, eth, arp_pkt, target_ip, in_port):
    target_mac = self.ip_to_mac[target_ip]
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

        #arp proto info
        arp_pkt = pkt.get_protocol(arp.arp)
        target_ip = arp_pkt.dst_ip

        #ipv4 proto info
        ip_pkt = pkt.get_protocol(ipv4.ipv4)
        parser = datapath.ofproto_parser

        dst = eth.dst
        src = eth.src
        ethertype = eth.ethertype

        if ethertype ==  ether_types.ETH_TYPE_IPV6:
            # self.logger.info("IPv6 packet detected, ignoring")
            return

        self.mac_to_port.setdefault(dpid, {})

        self.logger.info("packet in %s %s %s %s in_port=%s", hex(dpid), hex(ethertype), src, dst, msg.in_port)

        # learn a mac address to avoid FLOOD next time.
        self.mac_to_port[dpid][src] = msg.in_port

        if dpid == 1:
            if eth.ethertype == ether_types.ETH_TYPE_ARP: # this packet is ARP packet
                """
                fill in the code here for the ARP requests operation, creating and sending ARP replies.
                """
                if arp_pkt and arp_pkt.opcode == arp.ARP_REQUEST and target_ip is "192.168.1.1" or target_ip is "192.168.2.1":
                    self.arp_reply(datapath, eth, arp_pkt, target_ip, msg.in_port)
                return 
            elif eth.ethertype == ether_types.ETH_TYPE_IP: # this packet is IP packet
                """
                fill in the code here for the IP packets operation
                You must i) handle the packets coming to the controller with a packet_out message and then 
                ii) add an appropriate flow, modifying and using the add_flow function, in order the controller to not receive a packet with the same headers again. 
                """
                if ip_pkt:
                    self.logger.info("IP Packet received: %s", ip_pkt) #  ip_pkt.src, ip_pkt.dst

                    actions = [parser.OFPActionOutput(ofproto.ip_to_port(ip_pkt.dst))]

                    out = parser.OFPPacketOut(
                        datapath=datapath,
                        buffer_id=ofproto.OFP_NO_BUFFER,
                        in_port=msg.match['in_port'],
                        actions=actions,
                        data=msg.data)
                    datapath.send_msg(out)

                    self.add_flow(datapath, 1, "00:00:00:00:00:01", [datapath.ofproto_parser.OFPActionOutput(ip_to_port(ip_pkt.dst))])
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
