######################################################
# Program to monitor bundle traffic and save power   #
# Made by Botond Fulop                               #
######################################################

import time, csv, os, netaddr, paramiko 
from easysnmp import Session, EasySNMPError, snmp_get
from datetime import datetime , timedelta

class Interfaces:
     
     def __init__(self, index):
          self.if_index=index  #SNMP if index
          self.if_descr="" #if type
          self.if_speed="" #if bandwith 
          self.if_oper_status=""  #up(1), down(2),testing(3), unknown(4), dormant(5),notPresent(6), lowerLayerDown(7)
          self.in_octet=[]
          self.out_octet=[]
          self.in_utilization=[] #Interface IN utilization in percentage
          self.out_utilization=[] #Interface OUT utilization in percentage
          self.can_save_power=True  #Should be FALSE for mgmt and access interfaces or interfaces that should not be shutdown 
          self.if_run_cfg=""
          self.if_ip_address=""
          self.if_description=""
          #####################################
          self.whitch_bundle_member=""
          self.is_bundle=False
          self.in_utilization_in_bps=[]
          self.out_utilization_in_bps=[]
          
class MonitoredNode:
     node_names=[]

     def __init__(self, ip_address, community_string, snmp_version,idle_power_usage,name_of_bundle_interface,bundle_member_interfaces):
          self.ip_address = ip_address  
          self.community_string =  community_string
          self.snmp_version = snmp_version 
          self.name=""
          self.interfaces=[]
          self.only_up_physical_interfaces=[]
          self.idle_power_usage= idle_power_usage
 ############################## NEW ###################################
          self.name_of_bundle_interface=name_of_bundle_interface
          self.bundle_member_interfaces=bundle_member_interfaces
          self.active_bundle_member_interfaces=bundle_member_interfaces
          self.shutdown_bundle_member_interfaces=[]
          self.slice_is_up = True

     def poll_basic_info(self):
        try:
            name_with_domain=snmp_get('.1.3.6.1.2.1.1.5.0', hostname=self.ip_address, community=self.community_string, version=self.snmp_version).value
            self.name=name_with_domain.split(".",1)[0]
            MonitoredNode.node_names.append(self.name)
        except EasySNMPError as e:
            print(f"\033[1;33;40mAn error occurred with this node: {self.ip_address} during the basic poll SNMP session: {e}\033[0m")
        except Exception as e:
            print(f"\033[1;33;40mAn unexpected error occurred with this node during the basic poll: {self.ip_address} error: {e}\033[0m")

     def poll_interfaces(self):
        try:
            session = Session( hostname=self.ip_address, community=self.community_string, version=self.snmp_version) 
            indexes = session.walk('.1.3.6.1.2.1.2.2.1.1')
            descr= session.walk('.1.3.6.1.2.1.2.2.1.2')
            speed= session.walk('.1.3.6.1.2.1.2.2.1.5')
            oper_status= session.walk('.1.3.6.1.2.1.2.2.1.8')
            for item in indexes: 
                self.interfaces.append(Interfaces(item.value))
            for item in self.interfaces:
                #Getting IF_descr
                for element in descr:
                    search_index=element.oid.split('.')
                    search_index=search_index[-1]
                    if search_index == item.if_index:
                        item.if_descr=element.value
                #Getting IF_speeds 
                for element in speed:
                    search_index=element.oid.split('.')
                    search_index=search_index[-1]
                    if search_index == item.if_index:
                        item.if_speed=element.value
                #Getting IF_oper_status
                for element in oper_status:
                    search_index=element.oid.split('.')
                    search_index=search_index[-1]
                    if search_index == item.if_index:
                        item.if_oper_status=element.value
            #Selecting only up physical interfaces
            for item in self.interfaces:
                if "vlan" in item.if_descr.lower():
                    pass
                elif "loopback" in item.if_descr.lower():
                    pass
                elif "null" in item.if_descr.lower():
                    pass
                elif int(item.if_oper_status,10) == 1:  #up(1), down(2),testing(3), unknown(4), dormant(5),notPresent(6), lowerLayerDown(7)
                    self.only_up_physical_interfaces.append(item)
        except EasySNMPError as e:
            print(f"\033[1;33;40mAn error occurred with this node: {self.ip_address} during the interface poll SNMP session: {e}\033[0m") 
        except Exception as e:
            print(f"\033[1;33;40mAn unexpected error occurred with this node during the interface poll: {self.ip_address} error: {e}\033[0m")

############################################# CLASSES END #####################################################################
             
def create_node_instance(INVENTORY_PATH):
    nodes_list=[]
    with open(INVENTORY_PATH) as inventory:
        invcsv = csv.reader(inventory)
        for row in invcsv:
            ip_address = row[0]  #IP address or domain
            community_string = row[1]  #Community-string
            snmp_version = int(row[2]) #SNMP version
            idle_power_usage=int(row[3]) #Idle power usage
            name_of_bundle_interface=row[4]
            bundle_member_interfaces=row[5:]
            nodes_list.append(MonitoredNode(ip_address,community_string,snmp_version,idle_power_usage,name_of_bundle_interface,bundle_member_interfaces))
    return nodes_list 

#Reading interface configs from txt made by ansible playbook
def append_interface_info(FOLDER_PATH, nodes):
    file_names=os.listdir(FOLDER_PATH)
    for file_name in file_names:
        hostname = file_name.split(".",1)[0]
        for node in nodes:
            if node.name == hostname:
                with open(FOLDER_PATH +"/"+file_name, 'r') as read_obj:
                    read_input= read_obj.read()
                    current_section = ""
                    all_int_cfg = []
                    for line in read_input.splitlines():
                        if line.startswith("interface "):
                            if current_section:
                                all_int_cfg.append(current_section)
                            current_section = line
                        else:
                            current_section += "\n" + line
                    if current_section:
                        all_int_cfg.append(current_section)
                for interface in node.interfaces:
                    for int_cfg in all_int_cfg:
                        if interface.if_descr.lower() in int_cfg.lower():
                            interface.if_run_cfg = int_cfg
                    for item in node.bundle_member_interfaces:
                        if interface.if_descr.lower() == item.lower():
                            interface.whitch_bundle_member=node.name_of_bundle_interface
                    if interface.if_descr.lower() == node.name_of_bundle_interface.lower():
                        interface.is_bundle=True

#Extracting the info from the interface configs 
def extract_interface_info(nodes,MGMT_ACCESS_NETWORKS_PATH):
    for node in nodes:
        mgmt_or_access_network = []
        access_descriptions = ["acc", "access", "lan"]
        mgmt_descriptions = ["mgmt", "management"]
        with open(MGMT_ACCESS_NETWORKS_PATH) as inventory:
            invcsv = csv.reader(inventory)
            for row in invcsv:
                mgmt_or_access_network.append([row[0],row[1]])

        for interface in node.interfaces:
            for item in interface.if_run_cfg.split("\n"):
                if "ip address" in item and "no ip address" not in item:
                    interface.if_ip_address = format_mask_to_cidr(item.replace('ip address','').strip())
                if "description" in item:
                    interface.if_description = item.replace('description','').strip()
            for network in mgmt_or_access_network:
                if interface.if_ip_address == "":
                    pass
                else:
                    if netaddr.IPNetwork(interface.if_ip_address) in netaddr.IPNetwork(network[0]):
                        interface.can_save_power = False           
                for item in interface.if_description.lower().split(" "):
                    if item in mgmt_descriptions:
                        interface.can_save_power = False
                    elif item in access_descriptions:
                        interface.can_save_power = False

def format_mask_to_cidr(ip_with_mask):
    ip=ip_with_mask.split(" ",1)
    try:
        network = netaddr.IPNetwork(f'{ip[0]}/{ip[1]}')
        return str(ip[0]+"/"+str(network.prefixlen))
    except (ValueError, KeyError):
        return None

def poll_interface_traffic(node):
    max_number_counter32=4294967295 #For handling the counter overflow
    session = Session( hostname=node.ip_address, community=node.community_string, version=node.snmp_version)
    for item in node.only_up_physical_interfaces:
        ########### IN #############
        in_oct=session.get(f'.1.3.6.1.2.1.2.2.1.10.{item.if_index}')
        item.in_octet.append([int(in_oct.value), datetime.now()])
        #print(f"\033[2;30;41m{node.name} {item.if_descr} {item.if_index}\033[0m in octet counter:{item.in_octet[-1][0]}")
        number_of_in_measurments = len(item.in_octet)
        if number_of_in_measurments < 2:
            pass
        else:
            #print(type(item.in_octet[len(item.in_octet)-1][1]))
            in_time_difference = (item.in_octet[-1][1] - item.in_octet[-2][1]) 
            #print("Time difference",float(in_time_difference.total_seconds()*1000)) # in milli sec
            current_in_bits=int(item.in_octet[-1][0])*8
            previous_in_bits=int(item.in_octet[-2][0])*8
            if current_in_bits < previous_in_bits:
                current_in_bits = current_in_bits + (max_number_counter32 - previous_in_bits)
                current_in_utilization = int(float(current_in_bits) / float(in_time_difference.total_seconds())) #integer bit/s
                #current_in_utilization = float(current_in_bits) / float(in_time_difference.total_seconds())/1000 #Kbit/s  
                #print(f"Current in utilization:{current_in_utilization} Kbitps with bits in: {current_in_bits}")
                if current_in_utilization == 0:
                    now=datetime.now()
                    item.in_utilization.append([0, now]) #Interface utilization in percentage
                    item.in_utilization_in_bps.append([0, now]) #Interface utilization in bps
                else:
                    now=datetime.now()
                    item.in_utilization.append([int((current_in_utilization/int(item.if_speed))*100), now]) #Interface utilization in percentage
                    item.in_utilization_in_bps.append([current_in_utilization, now]) #Interface utilization in bps
            else:
                current_in_bits = current_in_bits - previous_in_bits
                current_in_utilization = int(float(current_in_bits) / float(in_time_difference.total_seconds())) #integer bit/s 
                #current_in_utilization = float(current_in_bits) / float(in_time_difference.total_seconds())/1000 #Kbit/s 
                #print(f"\033[2;30;47mCurrent in utilization:{int(current_in_utilization/1000)} Kbitps with bits in: {current_in_bits} time delta: {float(in_time_difference.total_seconds())} \033[0m") 
                if current_in_utilization == 0:
                    now=datetime.now()
                    item.in_utilization.append([0, now]) #Interface utilization in percentage
                    item.in_utilization_in_bps.append([0, now]) #Interface utilization in bps
                else:
                    now=datetime.now()
                    item.in_utilization.append([int((current_in_utilization/int(item.if_speed))*100), now]) #Interface utilization in percentage
                    item.in_utilization_in_bps.append([current_in_utilization, now]) #Interface utilization in bps

        if item.in_utilization and (item.is_bundle or item.whitch_bundle_member != ""):
            print(f"\033[2;30;41m{node.name} {item.if_descr}\033[0m \033[2;30;47mCurrent IN utilization: {item.in_utilization[-1][0]}%\033[0m")
            #print(f"\033[2;30;47m       \033[0m")
        #Keeping only max 100 measurments 
        #print(item.in_octet)
        if number_of_in_measurments > 100:
            item.in_octet.pop(0) 
        if len(item.in_utilization)>100:
            item.in_utilization.pop(0)
        if len(item.in_utilization_in_bps)>100:
            item.in_utilization_in_bps.pop(0)

        ########### OUT #############
        out_oct=session.get(f'.1.3.6.1.2.1.2.2.1.16.{item.if_index}')
        item.out_octet.append([int(out_oct.value), datetime.now()])
        #print(f"\033[2;30;42m{node.name} {item.if_descr} {item.if_index}\033[0m out octet counter:{item.out_octet[-1][0]}")
        number_of_out_measurments = len(item.out_octet)
        if number_of_out_measurments < 2:
            pass
        else:
            #print(type(item.out_octet[len(item.out_octet)-1][1]))
            out_time_difference = (item.out_octet[-1][1] - item.out_octet[-2][1]) 
            #print("Time difference",float(out_time_difference.total_seconds()*1000)) # in milli sec
            current_out_bits=int(item.out_octet[-1][0])*8
            previous_out_bits=int(item.out_octet[-2][0])*8
            if current_out_bits < previous_out_bits:
                current_out_bits = current_out_bits + (max_number_counter32 - previous_out_bits)
                current_out_utilization = int(float(current_out_bits) / float(out_time_difference.total_seconds())) #integer bit/s
                #current_out_utilization = float(current_out_bits) / float(out_time_difference.total_seconds())/1000 #Kbit/s  
                #print(f"Current out utilization:{current_out_utilization} Kbitps with bits out: {current_out_bits}")
                if current_out_utilization == 0:
                    now=datetime.now()
                    item.out_utilization.append([0, now]) #Interface utilization in percentage
                    item.out_utilization_in_bps.append([0, now]) #Interface utilization in bps
                else:
                    now=datetime.now()
                    item.out_utilization.append([int((current_out_utilization/int(item.if_speed))*100), now]) #Interface utilization in percentage
                    item.out_utilization_in_bps.append([current_out_utilization, now]) #Interface utilization in bps
            else:
                current_out_bits = current_out_bits - previous_out_bits
                current_out_utilization = int(float(current_out_bits) / float(out_time_difference.total_seconds())) #integer bit/s 
                #current_out_utilization = float(current_out_bits) / float(out_time_difference.total_seconds())/1000 #Kbit/s 
                #print(f"\033[2;30;47mCurrent out utilization:{int(current_out_utilization/1000)} Kbitps with bits out: {current_out_bits} time delta: {float(out_time_difference.total_seconds())} \033[0m")
                if current_out_utilization == 0:
                    now=datetime.now()
                    item.out_utilization.append([0, now]) #Interface utilization in percentage
                    item.out_utilization_in_bps.append([0, now]) #Interface utilization in bps
                else:
                    now=datetime.now()
                    item.out_utilization.append([int((current_out_utilization/int(item.if_speed))*100), now]) #Interface utilization in percentage
                    item.out_utilization_in_bps.append([current_out_utilization, now]) #Interface utilization in bps
        if item.out_utilization and (item.is_bundle or item.whitch_bundle_member != ""):
            print(f"\033[2;30;42m{node.name} {item.if_descr}\033[0m \033[2;30;47mCurrent OUT utilization: {item.out_utilization[-1][0]}%\033[0m")
        #Keeping only max 100 measurments 
        #print(item.out_octet)
        if number_of_out_measurments > 100:
            item.out_octet.pop(0) 
        if len(item.out_utilization)>100:
            item.out_utilization.pop(0)
        if len(item.out_utilization_in_bps)>100:
            item.out_utilization_in_bps.pop(0)

def check_if_there_are_enough_utilization_data(node,needed_number):
    for interface in node.only_up_physical_interfaces:
        if interface.whitch_bundle_member != "" or interface.is_bundle:
            if len(interface.in_utilization) < needed_number:
                return False
            elif len(interface.out_utilization) < needed_number:
                return False
    return True

def get_one_bundle_member_interface_speed(node):
    for interface in node.only_up_physical_interfaces:
        if interface.is_bundle:
            return int(int(interface.if_speed) / len(node.bundle_member_interfaces))

def shutdown_interface(node,selected_interface):
    try:
        ssh = paramiko.SSHClient()
        # Automatically add the server's host key
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            
        ssh.connect(node.ip_address, username=username, password=password)
        print(f"\nConnected to the {node.name} router.")

        # Start an interactive shell
        shell = ssh.invoke_shell()
        command="conf t\n"
        for interface in node.only_up_physical_interfaces:
            if interface.if_descr == selected_interface:
                command+="interface "+interface.if_descr+"\nshutdown\nexit\n"

        shell.send(command + "\n")
        time.sleep(2)

        output = shell.recv(65535).decode()
        print(output)
                
    except paramiko.AuthenticationException:
        print("Authentication failed. Please check the credentials.")
    except paramiko.SSHException as ssh_ex:
        print(f"Unable to establish SSH connection: {str(ssh_ex)}")
    except KeyboardInterrupt:
        print("Shutdown stopped by user.")
    finally:
        ssh.close()
    
def no_shut_interface(node,selected_interface):
    try:
        ssh = paramiko.SSHClient()
        # Automatically add the server's host key
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            
        ssh.connect(node.ip_address, username=username, password=password)
        print(f"\nConnected to the {node.name} router.")

        # Start an interactive shell
        shell = ssh.invoke_shell()
        command="conf t\n"
        for interface in node.only_up_physical_interfaces:
            if interface.if_descr == selected_interface:
                command+="interface "+interface.if_descr+"\nno shutdown\nexit\n"

        shell.send(command + "\n")
        time.sleep(2)

        output = shell.recv(65535).decode()
        print(output)
                
    except paramiko.AuthenticationException:
        print("Authentication failed. Please check the credentials.")
    except paramiko.SSHException as ssh_ex:
        print(f"Unable to establish SSH connection: {str(ssh_ex)}")
    except KeyboardInterrupt:
        print("Shutdown stopped by user.")
    finally:
        ssh.close()

def shutdown_slice(node,selected_slice):
    try:
        ssh = paramiko.SSHClient()
        # Automatically add the server's host key
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            
        ssh.connect(node.ip_address, username=username, password=password)
        print("Connected to the router.")

        # Start an interactive shell
        shell = ssh.invoke_shell()
        command="conf t\n"
        #command+="\nhw-module location 0/2/CPU0 slice  " + selected_slice + "  power-savings\nexit\n" #this should be the command if not simulating
        command+="do show ip interface brief" #simulating slice powersave
        shell.send(command + "\n")
        time.sleep(2)

        output = shell.recv(65535).decode()
        print(output)
                
    except paramiko.AuthenticationException:
        print("Authentication failed. Please check the credentials.")
    except paramiko.SSHException as ssh_ex:
        print(f"Unable to establish SSH connection: {str(ssh_ex)}")
    except KeyboardInterrupt:
        print("Shutdown stopped by user.")
    finally:
        ssh.close()

def no_shut_slice(node,selected_slice):
    try:
        ssh = paramiko.SSHClient()
        # Automatically add the server's host key
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            
        ssh.connect(node.ip_address, username=username, password=password)
        print("Connected to the router.")

        # Start an interactive shell
        shell = ssh.invoke_shell()
        command="conf t\n"
        #command+="\nno hw-module location 0/2/CPU0 slice " + selected_slice + " power-savings\n" #this should be the command if not simulating
        command+="do show ip interface brief" #simulating slice no powersave
        shell.send(command + "\n")
        time.sleep(2)

        output = shell.recv(65535).decode()
        print(output)

    except paramiko.AuthenticationException:
        print("Authentication failed. Please check the credentials.")
    except paramiko.SSHException as ssh_ex:
        print(f"Unable to establish SSH connection: {str(ssh_ex)}")
    except KeyboardInterrupt:
        print("Shutdown stopped by user.")
    finally:
        ssh.close()

def need_to_no_shut(node,one_interface_speed,from_how_many_cycles):
    active_port_number=len(node.active_bundle_member_interfaces)
    in_bundle_traffic_in_bps=0
    out_bundle_traffic_in_bps=0
    for item in node.active_bundle_member_interfaces:
        for interface in node.only_up_physical_interfaces:
            if item == interface.if_descr:
                for cycle in range(1,from_how_many_cycles+1):
                    in_bundle_traffic_in_bps+=interface.in_utilization_in_bps[-cycle][0]
                    out_bundle_traffic_in_bps+=interface.out_utilization_in_bps[-cycle][0]
    if (in_bundle_traffic_in_bps / from_how_many_cycles )/ one_interface_speed -(active_port_number-1) > 0.75 or (out_bundle_traffic_in_bps / from_how_many_cycles)/ one_interface_speed -(active_port_number-1) > 0.75:
        return True
    return False
            
def need_to_shutdown(node,one_interface_speed,from_how_many_cycles):
    active_port_number=len(node.active_bundle_member_interfaces)
    in_bundle_traffic_in_bps=0
    out_bundle_traffic_in_bps=0
    for item in node.active_bundle_member_interfaces:
        for interface in node.only_up_physical_interfaces:
            if item == interface.if_descr:
                for cycle in range(1,from_how_many_cycles+1):
                    in_bundle_traffic_in_bps+=interface.in_utilization_in_bps[-cycle][0]
                    out_bundle_traffic_in_bps+=interface.out_utilization_in_bps[-cycle][0]
    if (in_bundle_traffic_in_bps / from_how_many_cycles) / one_interface_speed -(active_port_number-1) <= -0.5 and (out_bundle_traffic_in_bps / from_how_many_cycles) / one_interface_speed -(active_port_number-1) <= -0.5:
        return True
    return False

def shutdown(nodes, ports_per_slice,selected_slice):
    for node in nodes:
        selected_interface = node.active_bundle_member_interfaces[-1]
        node.active_bundle_member_interfaces.pop(-1)
        node.shutdown_bundle_member_interfaces.append(selected_interface)
        shutdown_interface(node,selected_interface)
        if len(node.active_bundle_member_interfaces) <= ports_per_slice and node.slice_is_up:
            shutdown_slice(node,selected_slice)
            print("Slice is in powersave mode")
            node.slice_is_up = False

def no_shut(nodes, ports_per_slice,selected_slice):
    for node in nodes:
        selected_interface = node.shutdown_bundle_member_interfaces[-1]
        node.shutdown_bundle_member_interfaces.pop(-1)
        node.active_bundle_member_interfaces.append(selected_interface)
        if len(node.active_bundle_member_interfaces) > ports_per_slice and node.slice_is_up == False:
            no_shut_slice(node,selected_slice)
            node.slice_is_up = True
            print("Waiting 1 second for no slice powersave")
            time.sleep(1)
        no_shut_interface(node,selected_interface)

#Run the Ansible playbook before this script
if __name__=='__main__':
    try:
        #absolute path to the working directory 
        WORKING_DIR= '/home/botond/diplomatervezes2/'
        #other paths
        location_of_the_running_interfaces = WORKING_DIR+"bundle_interface_info"
        location_of_the_mgmt_and_access_csv = WORKING_DIR + "python_snmp/mgmt_and_access_networks.csv"
        location_of_the_node_infos=WORKING_DIR+'python_snmp/bundle_inventory.csv'
        #Credentials for SSH command executions
        username="Boti"
        password="Halozat"
        #Check if the ansible playbook collected the neccesarry information from the nodes
        if  os.path.isdir(location_of_the_running_interfaces) == False:
            raise Exception("Please run the Ansible playbook first")
        if not os.listdir(location_of_the_running_interfaces):
            raise Exception("Please run the Ansible playbook first, the interface_info folder is empty")
        
        #Setting up the nodes for monitoring
        nodes=create_node_instance(location_of_the_node_infos)
        for node in nodes:
            node.poll_basic_info()
            node.poll_interfaces()
            if node.name:
                print("\033[2;30;47mNode SNMP info:\033[0m",node.ip_address ,node.community_string, node.snmp_version)
                print("\033[2;30;47mThe device name is:\033[0m",node.name)
                print("\033[2;30;47mThe monitored Bundle is:\033[0m",node.name_of_bundle_interface)
                print("\033[2;30;47mThe Bundle member interfaces are:\033[0m",node.bundle_member_interfaces)
                print("\033[2;30;47mThe up interfaces:\033[0m")
                for item in node.only_up_physical_interfaces:
                    print(item.if_index, '-----', item.if_descr, '-----', item.if_speed, '-----', item.if_oper_status)
                print()
        append_interface_info(location_of_the_running_interfaces,nodes)
        extract_interface_info(nodes,location_of_the_mgmt_and_access_csv)
        print()
        #Monitoring the link utilizations 
        print(f'\033[2;30;47mMonitoring these nodes: {MonitoredNode.node_names}\033[0m') 
#################################### GLOBAL VARS #####################################################
        freq=5  #polling intervall
        have_enough_data=False
        start_time=datetime.now()
        last_noshut_time = datetime.now()
        last_shutdown_time = datetime.now()
        last_traffic_poll=datetime.now()
        min_links_in_bundle=1
        ports_per_slice=2
        one_interface_speed = get_one_bundle_member_interface_speed(nodes[0])
        from_how_many_cycles = 2
        selected_slice_number=1
########################################################################################################  
        time.sleep(freq)
        print("\033[2;30;47mTraffic of the Bundle interfaces:\033[0m")
        try: 
            while True:
                if datetime.now() -last_traffic_poll > timedelta(seconds=freq):
                    poll_interface_traffic(nodes[0]) #it is enough to monitor 1 node's in and out traffic
                    last_traffic_poll=datetime.now()
                    if datetime.now() - start_time > timedelta(seconds=20):
                            print("Checking for powersave options\n")
                            if have_enough_data == False:
                                print("Please wait, collecting more data...")
                                have_enough_data = check_if_there_are_enough_utilization_data(nodes[0],3) #2nd param is the number of utilization data needed for the program to start
                            else:
        ##################################################### NO SHUT CHECK ####################################################################################
                                if 0 < len(nodes[0].shutdown_bundle_member_interfaces) and datetime.now() - last_noshut_time > timedelta(seconds=10) and datetime.now() - last_shutdown_time > timedelta(seconds=10):
                                    #check if interface needs to be no shutted
                                    if need_to_no_shut(nodes[0],one_interface_speed,from_how_many_cycles):
                                        #if yes no shut the interface
                                        print("No shutting an interface")
                                        no_shut(nodes,ports_per_slice,selected_slice_number)
                                        last_noshut_time = datetime.now()
                                    
        ##################################################### SUTDOWN CHECK ####################################################################################
                                if min_links_in_bundle < len(nodes[0].active_bundle_member_interfaces) and datetime.now() - last_noshut_time > timedelta(seconds=40) and datetime.now() - last_shutdown_time > timedelta(seconds=20):
                                    #check if interface needs to be shutdown
                                    if need_to_shutdown(nodes[0],one_interface_speed,from_how_many_cycles):
                                        #if yes shutdown the interface
                                        print("Shutting down an interface") 
                                        shutdown(nodes,ports_per_slice,selected_slice_number)
                                        last_shutdown_time = datetime.now()
                print()
                time.sleep(1)
        except KeyboardInterrupt:
            print('Program stopped by user')
        except Exception as e:
            print(f'Unexpected error happened {e}')
    except Exception as e:
        print(f'Unexpected error happened {e}')