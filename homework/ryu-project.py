#!/usr/bin/python
#3581


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
from ryu.controller.handler import CONFIG_DISPATCHER
from ryu.controller.handler import set_ev_cls
from ryu.ofproto import ofproto_v1_0
from ryu.lib.mac import haddr_to_bin
from ryu.lib.packet import packet
from ryu.lib.packet import ethernet
from ryu.lib.packet import arp
from ryu.lib.packet import ipv4
from ryu.lib.packet import ether_types
from ryu.lib.packet import udp
from ryu.lib.packet import vlan

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
H2_IP = "192.168.2.2"
H2_MAC = "00:00:00:00:02:02"
H3_IP = "192.168.2.3"
H3_MAC = "00:00:00:00:02:03"
H4_IP = "192.168.1.3"
H4_MAC = "00:00:00:00:01:03"

ROUTER1_TOP_IP = "200.0.0.1"
ROUTER1_TOP_MAC = "00:00:00:00:04:01"
H5_IP = "200.0.0.2"
H5_MAC = "00:00:00:00:04:02"

ROUTING_TABLE = {
    0x1A: {
        H1_IP: 2,
        H2_IP: 1,
        H3_IP: 1,
        H4_IP: 2,
        H5_IP: 3
    },
    0x1B: {
        H1_IP: 1,
        H2_IP: 2,
        H3_IP: 2,
        H4_IP: 1,
        H5_IP: 1
    }
}

ARP_TABLE = {
    ROUTER1_LEFT_IP: ROUTER1_LEFT_MAC,
    ROUTER1_RIGHT_IP: ROUTER1_RIGHT_MAC,
    ROUTER1_TOP_IP: ROUTER1_TOP_MAC,
    ROUTER2_LEFT_IP: ROUTER2_LEFT_MAC,
    ROUTER2_RIGHT_IP: ROUTER2_RIGHT_MAC,
    H1_IP: H1_MAC,
    H2_IP: H2_MAC,
    H3_IP: H3_MAC,
    H4_IP: H4_MAC,
    H5_IP: H5_MAC
}

ROUTER1_SUBNET = "192.168.1.0"
ROUTER2_SUBNET = "192.168.2.0"
ROUTER1_TOP_SUBNET = "200.0.0.0"

# VLANID mapping for switches: for dpid 0x2, identity; for dpid 0x3, swap 100<->200
VLANID = {
    0x2: {100: 100, 200: 200},
    0x3: {100: 200, 200: 100}
}

nat = {}
reverse_nat = {}
next_port = 12345


class SimpleSwitch(app_manager.RyuApp):
    OFP_VERSIONS = [ofproto_v1_0.OFP_VERSION]

    
    
    def __init__(self, *args, **kwargs):
        super(SimpleSwitch, self).__init__(*args, **kwargs)
        self.mac_to_port = {}

    @set_ev_cls(ofp_event.EventOFPSwitchFeatures, CONFIG_DISPATCHER)
    def switch_features_handler(self, ev):
        datapath = ev.msg.datapath
        dpid = datapath.id
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser

        #proactive flow for router 2
        if dpid == 0x1B:
            match = datapath.ofproto_parser.OFPMatch(
                        dl_type=ether_types.ETH_TYPE_IP,
                        nw_proto=17,  # UDP protocol number
                        nw_dst=ROUTER1_TOP_SUBNET,
                        nw_dst_mask=24
                    )
            actions = [
                    datapath.ofproto_parser.OFPActionSetDlSrc(ROUTER2_LEFT_MAC),
                    datapath.ofproto_parser.OFPActionSetDlDst(ROUTER1_RIGHT_MAC),
                    datapath.ofproto_parser.OFPActionOutput(1)
                ]
            self.add_flow(datapath, match, actions)

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
        # L2 forwarding
        ofproto = datapath.ofproto
        data = None
        if msg.buffer_id == ofproto.OFP_NO_BUFFER:
            data = msg.data
        out = datapath.ofproto_parser.OFPPacketOut(
            datapath=datapath,
            buffer_id=msg.buffer_id,
            in_port=in_port,
            actions=actions,
            data=data
        )
        datapath.send_msg(out)

    def add_nat(self, internal_ip, internal_port):
        global next_port
        key = (internal_ip, internal_port)
        if key in nat:
            return nat[key]
        external = (ROUTER1_TOP_IP, next_port)
        nat[key] = external
        reverse_nat[external] = key
        next_port += 1
        # nat.get((ip, port))
        # reverse_nat.get((ip, port))
        return external

    def lookup_external(self, ROUTER1_TOP_IP, external_port):
        key = (ROUTER1_TOP_IP, external_port)
        if key in reverse_nat:
            return reverse_nat[key]
        return None

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
        udp_pkt = pkt.get_protocol(udp.udp)
        vlan_pkt = pkt.get_protocol(vlan.vlan)

        self.mac_to_port.setdefault(dpid, {})

        if dpid in (0x1A, 0x1B):
            self.logger.info("packet in %s %s %s %s in_port=%s", hex(dpid).ljust(4), hex(ethertype), src, dst, msg.in_port)

        # learn a mac address to avoid FLOOD next time.
        self.mac_to_port[dpid][src] = msg.in_port

        if dpid == 0x1A:
            if ethertype == ether_types.ETH_TYPE_ARP: 
                if arp_pkt.dst_ip == ROUTER1_LEFT_IP or arp_pkt.dst_ip == ROUTER1_TOP_IP:
                    self.arp_reply(datapath, eth, arp_pkt, msg.in_port)
                return
            elif ethertype == ether_types.ETH_TYPE_IP:
                
                #do not receive reversed nat packets (flow is added together with outbound nat)
                if ip_pkt.dst == ROUTER1_TOP_IP:
                    return

                out_port = ROUTING_TABLE[dpid][ip_pkt.dst]

                if out_port == 3:
                    print(f"[DEBUG] out_port=3: src_ip={ip_pkt.src}, dst_ip={ip_pkt.dst}, src_mac={src}, dst_mac={dst}, udp_src_port={udp_pkt.src_port if udp_pkt else 'N/A'}, udp_dst_port={udp_pkt.dst_port if udp_pkt else 'N/A'}")
                    if not udp_pkt:
                        self.logger.info("[0x1A] Non-UDP packet on port 3, dropping")
                        return
                    router_mac = ROUTER1_TOP_MAC
                    dst_mac = H5_MAC
                    match = datapath.ofproto_parser.OFPMatch(
                        dl_type=ether_types.ETH_TYPE_IP,
                        nw_proto=17,
                        nw_dst=ROUTER1_TOP_SUBNET,
                        nw_dst_mask=24,
                        nw_src=ip_pkt.src,
                        tp_src=udp_pkt.src_port, #match all ports to avoid conflicts
                        tp_dst=udp_pkt.dst_port #maybe not needed, src port is random
                    )
                    # Use add_nat to get (external_ip, external_port)
                    external_ip, new_src_port = self.add_nat(ip_pkt.src, udp_pkt.src_port)
                    self.logger.info(f"NAT table updated: ({ip_pkt.src}, {udp_pkt.src_port}) -> ({external_ip}, {new_src_port})")

                    actions = [
                        datapath.ofproto_parser.OFPActionSetDlSrc(router_mac),
                        datapath.ofproto_parser.OFPActionSetDlDst(dst_mac),
                        datapath.ofproto_parser.OFPActionSetNwSrc(external_ip),
                        datapath.ofproto_parser.OFPActionSetTpSrc(new_src_port),
                        datapath.ofproto_parser.OFPActionOutput(out_port)
                    ]

                    self.modify_and_send_ip_packet(datapath, msg.in_port, pkt, actions, out_port)
                    self.add_flow(datapath, match, actions)
                    
                    #now add the reverse NAT entry flow
                    internal = self.lookup_external(external_ip, new_src_port)
                    if internal:
                        internal_ip, internal_port = internal
                        self.logger.info(f"Reverse NAT: ({external_ip}, {new_src_port}) -> ({internal_ip}, {internal_port})")
                    else:
                        self.logger.info(f"No reverse NAT mapping found for {(internal_ip, internal_port)}, dropping packet")
                        return

                    out_port = ROUTING_TABLE[dpid][internal_ip]
                    if out_port == 1:
                        router_mac = ROUTER1_RIGHT_MAC
                    elif out_port == 2:
                        router_mac = ROUTER1_LEFT_MAC
                    
                    dst_mac = ARP_TABLE[internal_ip]

                    match = datapath.ofproto_parser.OFPMatch(
                            dl_type=ether_types.ETH_TYPE_IP,
                            nw_proto=17,
                            nw_src=ip_pkt.dst,
                            nw_dst=ROUTER1_TOP_IP, #of course specifix ip
                            tp_dst=new_src_port # match on the outer stuff
                        )
                    actions = [
                        datapath.ofproto_parser.OFPActionSetDlSrc(router_mac),
                        datapath.ofproto_parser.OFPActionSetDlDst(dst_mac),
                        datapath.ofproto_parser.OFPActionSetNwDst(internal_ip),
                        datapath.ofproto_parser.OFPActionSetTpDst(internal_port),
                        datapath.ofproto_parser.OFPActionOutput(out_port)
                    ]

                elif(out_port == 1):
                    router_mac = ROUTER1_RIGHT_MAC
                    dst_mac = ROUTER2_LEFT_MAC
                    match = datapath.ofproto_parser.OFPMatch(
                        dl_type=ether_types.ETH_TYPE_IP,
                        nw_dst=ROUTER2_SUBNET,
                        nw_dst_mask=24
                    )
                    actions = [
                        datapath.ofproto_parser.OFPActionSetDlSrc(router_mac),
                        datapath.ofproto_parser.OFPActionSetDlDst(dst_mac),
                        datapath.ofproto_parser.OFPActionOutput(out_port)
                    ]
                else:
                    router_mac = ROUTER1_LEFT_MAC
                    dst_mac = ARP_TABLE[ip_pkt.dst]
                    match = datapath.ofproto_parser.OFPMatch(
                        dl_type=ether_types.ETH_TYPE_IP,
                        nw_dst=ip_pkt.dst
                    )
                    actions = [
                        datapath.ofproto_parser.OFPActionSetDlSrc(router_mac),
                        datapath.ofproto_parser.OFPActionSetDlDst(dst_mac),
                        datapath.ofproto_parser.OFPActionOutput(out_port)
                    ]

                self.logger.info(f"[DPID {hex(dpid)}] {msg.in_port} -> {out_port}, "
                                 f"{router_mac} -> {dst_mac}, "
                                 f"{ip_pkt.src} -> {ip_pkt.dst}")

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

                if(out_port == 1):
                    router_mac = ROUTER2_LEFT_MAC
                    dst_mac = ROUTER1_RIGHT_MAC
                    match = datapath.ofproto_parser.OFPMatch(
                        dl_type=ether_types.ETH_TYPE_IP,
                        nw_dst=ROUTER1_SUBNET,
                        nw_dst_mask=24
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
                 
        #logic for both switches is exactly the same, only VLANID's must be swapped so I use a dictionary for vlanids and fuse the switch logic
        if dpid == 0x2 or dpid == 0x3:
            flood_flag = False
            # Rx (from trunk port)
            if msg.in_port == 1:
                if vlan_pkt is None:
                    self.logger.warning(f"Untagged packet received on trunk port (dpid {dpid}), dropping.")
                    return
                self.logger.info(f"[DPID {hex(dpid)}] Received packet on trunk port (VLAN {vlan_pkt.vid})")
                match = datapath.ofproto_parser.OFPMatch(
                    in_port=msg.in_port,
                    dl_vlan=vlan_pkt.vid
                )
                if vlan_pkt.vid == VLANID[dpid][200]:
                    #hm this flow will be added even in flooding situations (early),
                    #this is not a problem because after flooding we will know where to send,
                    #but realistically there is no way to differentiate flooding from normal traffic
                    #on another switch except if we know our host mac addresses in advance
                    #but that is the whole reason for the flooding
                    #or if we use a global variable to check if we are flooding like this:
                    flood_flag = True
                    out_port = 4
                    actions = [
                        datapath.ofproto_parser.OFPActionStripVlan(),
                        datapath.ofproto_parser.OFPActionOutput(out_port)
                    ]
                elif vlan_pkt.vid == VLANID[dpid][100]:
                    match = datapath.ofproto_parser.OFPMatch(
                        in_port=msg.in_port,
                        dl_vlan=vlan_pkt.vid,
                        dl_dst=haddr_to_bin(dst)
                    )
                    if dst in self.mac_to_port[dpid]:
                        out_port = self.mac_to_port[dpid][dst]
                    else:
                        out_port = ofproto.OFPP_FLOOD

                    if out_port == 2 or out_port == 3:
                        actions = [
                            datapath.ofproto_parser.OFPActionStripVlan(),
                            datapath.ofproto_parser.OFPActionOutput(out_port)
                        ]
                    elif out_port == ofproto.OFPP_FLOOD or out_port == 4:
                        flood_flag = True
                        self.logger.info(f"[DPID {hex(dpid)}] Flooding packet from trunk port (VLAN {vlan_pkt.vid})")
                        actions = [
                            datapath.ofproto_parser.OFPActionStripVlan(),
                            datapath.ofproto_parser.OFPActionOutput(2),
                            datapath.ofproto_parser.OFPActionOutput(3)
                        ]
            # Tx (to trunk port)
            elif msg.in_port == 4:
                out_port = 1
                match = datapath.ofproto_parser.OFPMatch(in_port=msg.in_port)
                actions = [
                    datapath.ofproto_parser.OFPActionVlanVid(VLANID[dpid][200]),
                    datapath.ofproto_parser.OFPActionOutput(out_port)
                ]
            # Access ports (2 or 3)
            else:  # msg.in_port is 2 or 3
                match = datapath.ofproto_parser.OFPMatch(
                    in_port=msg.in_port,
                    dl_dst=haddr_to_bin(dst)
                )
                if dst in self.mac_to_port[dpid]:
                    out_port = self.mac_to_port[dpid][dst]
                else:
                    out_port = ofproto.OFPP_FLOOD

                if out_port == ofproto.OFPP_FLOOD or out_port == 4:
                    flood_flag = True
                    self.logger.info(f"[DPID {hex(dpid)}] Flooding packet from access port {msg.in_port}")
                    # actions list are executed in order...
                    if msg.in_port == 2:
                        actions = [
                            datapath.ofproto_parser.OFPActionOutput(3),
                            datapath.ofproto_parser.OFPActionVlanVid(VLANID[dpid][100]),
                            datapath.ofproto_parser.OFPActionOutput(1)
                        ]
                    else:  # if msg.in_port == 3
                        actions = [
                            datapath.ofproto_parser.OFPActionOutput(2),
                            datapath.ofproto_parser.OFPActionVlanVid(VLANID[dpid][100]),
                            datapath.ofproto_parser.OFPActionOutput(1)
                        ]
                elif out_port == 1:
                    self.logger.info(f"[DPID {hex(dpid)}] Sending packet to trunk port (from access port {msg.in_port})")
                    actions = [
                        datapath.ofproto_parser.OFPActionVlanVid(VLANID[dpid][100]),
                        datapath.ofproto_parser.OFPActionOutput(out_port)
                    ]
                else:
                    actions = [
                        datapath.ofproto_parser.OFPActionOutput(out_port)
                    ]

                self.logger.info(f"[DPID {hex(dpid)}] {msg.in_port} -> {out_port}, "
                                        f"{src} -> {dst}, VLANID {vlan_pkt.vid if vlan_pkt else 'None'}")

            self.L2_send(datapath, msg.in_port, actions, msg)

            #if flooding to neighbor on same vlan but other switch do not add a flow
            if flood_flag:
                flood_flag = False
            else:
                self.add_flow(datapath, match, actions)
            return
        
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

