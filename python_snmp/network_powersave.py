######################################################
# Program to monitor traffic and save power          #
# Made by Botond Fulop                               #
######################################################
import time, csv, os, netaddr, networkx, matplotlib.pyplot, paramiko 
from easysnmp import Session, EasySNMPError, snmp_get
from datetime import datetime , timedelta
from multiprocessing import Process


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
          self.last_noshutdown=""#not in use yet
          self.can_save_power=True  #Should be FALSE for mgmt and access interfaces or interfaces that should not be shutdown 
          self.if_run_cfg=""
          self.if_ip_address=""
          self.if_description=""
          
class MonitoredNode:
     node_names=[]

     def __init__(self, ip_address, community_string, snmp_version,idle_power_usage):
          self.ip_address = ip_address  
          self.community_string =  community_string
          self.snmp_version = snmp_version 
          self.name=""
          self.interfaces=[]
          self.only_up_physical_interfaces=[]
          self.has_access_interface = False # If node has access int it should not be shutdown
          self.neighbour_nodes=[] #The name of the neighbor and the neighbour's interface
          self.idle_power_usage= idle_power_usage

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
                elif "bundle" in item.if_descr.lower():
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
            nodes_list.append(MonitoredNode(ip_address,community_string,snmp_version,idle_power_usage))
    return nodes_list 

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
                    item.in_utilization.append([0, datetime.now()]) #Interface utilization in percentage
                else:
                    item.in_utilization.append([int((current_in_utilization/int(item.if_speed))*100), datetime.now()]) #Interface utilization in percentage
            else:
                current_in_bits = current_in_bits - previous_in_bits
                current_in_utilization = int(float(current_in_bits) / float(in_time_difference.total_seconds())) #integer bit/s 
                #current_in_utilization = float(current_in_bits) / float(in_time_difference.total_seconds())/1000 #Kbit/s 
                #print(f"\033[2;30;47mCurrent in utilization:{int(current_in_utilization/1000)} Kbitps with bits in: {current_in_bits} time delta: {float(in_time_difference.total_seconds())} \033[0m") 
                if current_in_utilization == 0:
                    item.in_utilization.append([0, datetime.now()]) #Interface utilization in percentage
                else:
                    item.in_utilization.append([int((current_in_utilization/int(item.if_speed))*100), datetime.now()]) #Interface utilization in percentage
        if item.in_utilization:
            print(f"\033[2;30;41m{node.name} {item.if_descr}\033[0m \033[2;30;47mCurrent IN utilization: {item.in_utilization[-1][0]}%\033[0m")
            #print(f"\033[2;30;47m       \033[0m")
        #Keeping only max 100 measurments 
        #print(item.in_octet)
        if number_of_in_measurments > 100:
            item.in_octet.pop(0) 
        if len(item.in_utilization)>100:
            item.in_utilization.pop(0)


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
                    item.out_utilization.append([0, datetime.now()]) #Interface utilization in percentage
                else:
                    item.out_utilization.append([int((current_out_utilization/int(item.if_speed))*100), datetime.now()]) #Interface utilization in percentage
            else:
                current_out_bits = current_out_bits - previous_out_bits
                current_out_utilization = int(float(current_out_bits) / float(out_time_difference.total_seconds())) #integer bit/s 
                #current_out_utilization = float(current_out_bits) / float(out_time_difference.total_seconds())/1000 #Kbit/s 
                #print(f"\033[2;30;47mCurrent out utilization:{int(current_out_utilization/1000)} Kbitps with bits out: {current_out_bits} time delta: {float(out_time_difference.total_seconds())} \033[0m")
                if current_out_utilization == 0:
                    item.out_utilization.append([0, datetime.now()]) #Interface utilization in percentage
                else:
                    item.out_utilization.append([int((current_out_utilization/int(item.if_speed))*100), datetime.now()]) #Interface utilization in percentage
        if item.out_utilization:
            print(f"\033[2;30;42m{node.name} {item.if_descr}\033[0m \033[2;30;47mCurrent OUT utilization: {item.out_utilization[-1][0]}%\033[0m")
        #Keeping only max 100 measurments 
        #print(item.out_octet)
        if number_of_out_measurments > 100:
            item.out_octet.pop(0) 
        if len(item.out_utilization)>100:
            item.out_utilization.pop(0)
  
def format_mask_to_cidr(ip_with_mask):
    ip=ip_with_mask.split(" ",1)
    try:
        
        network = netaddr.IPNetwork(f'{ip[0]}/{ip[1]}')
        return str(ip[0]+"/"+str(network.prefixlen))

    except (ValueError, KeyError):
        return None

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
                        if network[1].lower() in access_descriptions:
                             node.has_access_interface = True
                for item in interface.if_description.lower().split(" "):
                    if item in mgmt_descriptions:
                        interface.can_save_power = False
                    elif item in access_descriptions:
                        interface.can_save_power = False
                        node.has_access_interface = True

def bulding_the_network_topology(nodes):
    edge_list=[]
    for node in nodes:
        for interface in node.only_up_physical_interfaces:
            if interface.can_save_power:
                for checked_node in nodes:
                    if node.name != checked_node.name:
                        for checked_interface in checked_node.only_up_physical_interfaces:
                            if netaddr.IPNetwork(interface.if_ip_address) in netaddr.IPNetwork(checked_interface.if_ip_address):
                                edge_list.append((node.name, checked_node.name))
                                node.neighbour_nodes.append([checked_node.name , checked_interface.if_descr])
    return edge_list

def plot_the_graph_of_nodes(list_of_directed_nodes, nodes_with_access_interface):
    # Creating a graph and getting ready to plot it
    G = networkx.DiGraph()
    G.add_edges_from(list_of_directed_nodes)
    pos = networkx.spring_layout(G)
    
    node_colors = {node: 'tab:red' for node in nodes_with_access_interface}  # Define node colors for nodes_with_access_interface
    default_color = 'tab:blue'  # Default node color
    
    options = {"edgecolors": "black", "node_size": 900, "alpha": 1}
    
    # Set the node color based on the node name
    node_color = [node_colors.get(node, default_color) for node in G.nodes()]
    
    networkx.draw_networkx_nodes(G, pos, node_color=node_color, **options)
    networkx.draw_networkx_edges(G, pos, edgelist=G.edges(), arrowsize=20, width=1, edge_color="black",min_target_margin=12)
    networkx.draw_networkx_labels(G, pos, font_color="whitesmoke")
    
    # Set the title for the figure
    matplotlib.pyplot.title("This is the network topology")
    
    # Plot the graph
    matplotlib.pyplot.show()

def shutdown_a_node_interfaces(nodes,shut_node_name,username, password):
    shutdown_interfaces=[]
    for node in nodes:
        if node.name == shut_node_name:
            try:
                ssh = paramiko.SSHClient()
                # Automatically add the server's host key
                ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
                    
                ssh.connect(node.ip_address, username=username, password=password)
                print("\nConnected to the router.")

                # Start an interactive shell
                shell = ssh.invoke_shell()
                command="conf t\n"
                for interface in node.only_up_physical_interfaces:
                    if interface.can_save_power:
                        command+="interface "+interface.if_descr+"\nshutdown\nexit\n"
                        shutdown_interfaces.append(interface.if_descr)


                shell.send(command + "\n")
                time.sleep(4)


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
        

    #return [shut_node_name,shutdown_interfaces]

def powerup_a_node_interfaces(nodes,powerup_node_name,username, password): 
    for node in nodes:
        if node.name == powerup_node_name:
            shutdown_interfaces=[]
            for inteface in node.only_up_physical_interfaces:
                if inteface.can_save_power:
                    shutdown_interfaces.append(inteface.if_descr)
            try:
                ssh = paramiko.SSHClient()
                # Automatically add the server's host key
                ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
                    
                ssh.connect(node.ip_address, username=username, password=password)
                print("\nConnected to the router.")

                # Start an interactive shell
                shell = ssh.invoke_shell()
                command="conf t\n"
                for interface in shutdown_interfaces:
                    command+="interface "+interface+"\nno shutdown\nexit\n"

                shell.send(command + "\n")
                time.sleep(4)

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

def set_node_ospf_link_cost_to_max(nodes,shut_node_name,username, password):
    max_cost_interfaces=[]
    for node in nodes:
        if node.name == shut_node_name:
            try:
                ssh = paramiko.SSHClient()
                # Automatically add the server's host key
                ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
                    
                ssh.connect(node.ip_address, username=username, password=password)
                print("\nConnected to the router.")

                # Start an interactive shell
                shell = ssh.invoke_shell()
                command="conf t\n"
                for interface in node.only_up_physical_interfaces:
                    if interface.can_save_power:
                        command+="interface "+interface.if_descr+"\nip ospf cost 65535\nexit\n"
                        max_cost_interfaces.append(interface.if_descr)


                shell.send(command + "\n")
                time.sleep(4)


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

    #return [shut_node_name,max_cost_interfaces]

def set_node_ospf_link_cost_to_normal(nodes,powerup_node_name,username, password): 
    for node in nodes:
        if node.name == powerup_node_name:
            max_cost_interfaces=[]
            for inteface in node.only_up_physical_interfaces:
                if inteface.can_save_power:
                    max_cost_interfaces.append(inteface.if_descr)
            try:
                ssh = paramiko.SSHClient()
                # Automatically add the server's host key
                ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
                    
                ssh.connect(node.ip_address, username=username, password=password)
                print("\nConnected to the router.")

                # Start an interactive shell
                shell = ssh.invoke_shell()
                command="conf t\n"
                for interface in max_cost_interfaces:
                    command+="interface "+interface+"\nno ip ospf cost 65535\nexit\n"

                shell.send(command + "\n")
                time.sleep(4)

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

def set_neighbour_nodes_ospf_link_cost_to_max(nodes,shut_node_name,username, password):
    for node in nodes:
        if node.name == shut_node_name:
            for neighbor in node.neighbour_nodes:
                for neighbor_node in nodes:
                    if neighbor_node.name == neighbor[0]:
                        try:
                            ssh = paramiko.SSHClient()
                            # Automatically add the server's host key
                            ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
                                
                            ssh.connect(neighbor_node.ip_address, username=username, password=password)
                            print("\nConnected to the router.")

                            # Start an interactive shell
                            shell = ssh.invoke_shell()
                            command="conf t\n"
                            for interface in neighbor_node.only_up_physical_interfaces:
                                if interface.if_descr == neighbor[1]:
                                    command+="interface "+interface.if_descr+"\nip ospf cost 65535\nexit\n"

                            shell.send(command + "\n")
                            time.sleep(4)

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

def set_neighbour_nodes_ospf_link_cost_to_normal(nodes,powerup_node_name,username, password):
    for node in nodes:
        if node.name == powerup_node_name:
            for neighbor in node.neighbour_nodes:
                for neighbor_node in nodes:
                    if neighbor_node.name == neighbor[0]:
                        try:
                            ssh = paramiko.SSHClient()
                            # Automatically add the server's host key
                            ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
                                
                            ssh.connect(neighbor_node.ip_address, username=username, password=password)
                            print("\nConnected to the router.")

                            # Start an interactive shell
                            shell = ssh.invoke_shell()
                            command="conf t\n"
                            for interface in neighbor_node.only_up_physical_interfaces:
                                if interface.if_descr == neighbor[1]:
                                    command+="interface "+interface.if_descr+"\nno ip ospf cost 65535\nexit\n"

                            shell.send(command + "\n")
                            time.sleep(4)

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

def check_if_there_are_enough_utilization_data(nodes,needed_number):
    for node in nodes:
        for interface in node.only_up_physical_interfaces:
            if interface.can_save_power:
                if len(interface.in_utilization) < needed_number:
                    return False
                elif len(interface.out_utilization) < needed_number:
                    return False
    return True

def is_every_transport_link_under_x_utilization(nodes,max_util,for_number_of_polling_cycles):
    for node in nodes:
        for interface in node.only_up_physical_interfaces:
            if interface.can_save_power:
                for cycle in range(1,for_number_of_polling_cycles+1):
                    if interface.in_utilization[-cycle][0] >= max_util:
                        return False
                    if interface.out_utilization[-cycle][0] >= max_util:
                        return False
    return True

def is_any_link_above_a_threshold(nodes,threshold_utilization,for_number_of_polling_cycles):
    for node in nodes:
        for interface in node.only_up_physical_interfaces:
            if interface.can_save_power:
                in_above_treshold_for_given_cycles=True
                out_above_treshold_for_given_cycles=True
                for cycle in range(1,for_number_of_polling_cycles+1):
                    if interface.in_utilization[-cycle][0] < threshold_utilization:
                        in_above_treshold_for_given_cycles *= False
                    if interface.out_utilization[-cycle][0] < threshold_utilization:
                        out_above_treshold_for_given_cycles *= False
                if bool(in_above_treshold_for_given_cycles) or bool(out_above_treshold_for_given_cycles):
                    return True
    return False

def check_if_any_node_can_be_removed(current_edges,nodes_with_access_interface,transport_nodes,powered_down_nodes):
    removable = which_node_can_be_removed_from_graph(current_edges,nodes_with_access_interface,transport_nodes,powered_down_nodes)
    if removable:
        return True, removable
    return False, []

def remove_node_from_graph(removed_node,current_edges):
    new_edges = [edge for edge in current_edges if removed_node not in edge]
    return new_edges 

def do_all_access_have_routes_to_eachother(graph_edges, access_nodes):
    G = networkx.DiGraph(graph_edges)
    for node in access_nodes:
        for checked_node in access_nodes:
            if node != checked_node:
                if networkx.has_path(G, node, checked_node)==False:
                    return False
    return True

def which_node_can_be_removed_from_graph(current_edges,access_nodes,transport_nodes,powered_down_nodes):
    nodes_that_can_be_removed=[]
    for node in transport_nodes:
        if node not in powered_down_nodes:
            test_edges=remove_node_from_graph(node,current_edges)
            if are_nodes_in_graph(test_edges,access_nodes):  
                if do_all_access_have_routes_to_eachother(test_edges,access_nodes):
                    nodes_that_can_be_removed.append(node)
    return nodes_that_can_be_removed

def are_nodes_in_graph(graph_edges, nodes_to_check):
    all_nodes = set(node for edge in graph_edges for node in edge)
    return all(node in all_nodes for node in nodes_to_check)

def select_candidate_for_shutdown(nodes,candidates,for_number_of_polling_cycles,min_threshold):
    possible_candidates=select_nodes_with_low_if_utilization(nodes,candidates,for_number_of_polling_cycles,min_threshold)
    print("These are the possible candidates for shutdown:",possible_candidates)
    possible_candidates_idle_power_usage=0
    if possible_candidates:
        selected_candidate=""
        for node in nodes:
            for candidate in possible_candidates:
                if node.name == candidate:
                    if node.idle_power_usage > possible_candidates_idle_power_usage:
                        possible_candidates_idle_power_usage=node.idle_power_usage
                        selected_candidate = candidate
        if selected_candidate:
            print("Selected candidate is:",selected_candidate)
            return selected_candidate
        else:
            print("Error in select_candidate_for_shutdown 1st if")         
    else:
        for node in nodes:
            for candidate in candidates:
                if node.name == candidate:
                    if possible_candidates:
                        possible_candidates.append(candidate)
                        possible_candidates_idle_power_usage=node.idle_power_usage
                else:
                    if node.idle_power_usage == possible_candidates_idle_power_usage:
                        possible_candidates.append(candidate)
                    elif node.idle_power_usage > possible_candidates_idle_power_usage:
                        possible_candidates=[candidate]
                        possible_candidates_idle_power_usage=node.idle_power_usage
        if possible_candidates:
            print("Selected candidate is:",possible_candidates[0])
            return possible_candidates[0]
        else:
            print("Error in select_candidate_for_shutdown 2nd if")

def select_nodes_with_low_if_utilization(nodes,candidates,for_number_of_polling_cycles,min_threshold):
    low_utilised_nodes=[]
    for node in nodes:
        for candidate in candidates:
            if node.name == candidate:
                is_under_threshold=True
                for interface in node.only_up_physical_interfaces:
                    if interface.can_save_power:
                        for cycle in range(1,for_number_of_polling_cycles+1):
                            if interface.in_utilization[-cycle][0] > min_threshold and interface.out_utilization[-cycle][0] > min_threshold:
                                is_under_threshold=False
                if is_under_threshold:
                    print(candidate,"is under the threshold.")
                    low_utilised_nodes.append(candidate)
                else:
                    print("No candidate is under the threshold.")
    return low_utilised_nodes
    
def shutdown_node(nodes,shut_node_name,username, password,time_between_cost_set_and_shutdown):
    set_node_ospf_link_cost_to_max(nodes,shut_node_name,username, password)
    set_neighbour_nodes_ospf_link_cost_to_max(nodes,shut_node_name,username,password)
    time.sleep(time_between_cost_set_and_shutdown)
    shutdown_a_node_interfaces(nodes,shut_node_name,username,password)
    #node can be shutdown/put to powersave here

def select_candidate_for_powerup(nodes,powered_down_nodes,threshold):
#check witch node has more neighbous above the threshold
    if len(powered_down_nodes)==1:
        return powered_down_nodes[0]
    current_number_of_neighbours_above_threshold=0
    current_candidate=""
    for candidate in powered_down_nodes:
        number_of_neighbours_above_threshold=0
        for node in nodes:
            if node.name == candidate:
                for neighbour in node.neighbour_nodes:
                            for neighbour_node in nodes:
                                if neighbour_node.name == neighbour[0]:
                                    for interface in neighbour_node.only_up_physical_interfaces:
                                        if interface.if_descr == neighbour[1]:
                                            if interface.in_utilization[-1][0] >= threshold:
                                                number_of_neighbours_above_threshold+=1
                                            if interface.out_utilization[-1][0] >= threshold:
                                                number_of_neighbours_above_threshold+=1 
        if current_candidate == "":
            current_candidate = candidate
            current_number_of_neighbours_above_threshold = number_of_neighbours_above_threshold
        elif current_number_of_neighbours_above_threshold < number_of_neighbours_above_threshold:
            current_candidate = candidate
            current_number_of_neighbours_above_threshold = number_of_neighbours_above_threshold
    print("Selected candidate is:",current_candidate)
    return current_candidate

def powerup_a_node(nodes,selected_for_powerup,username, password):
    #node can be poweredup/put to normal mode here
    #time.sleep(comeback_time) #waiting for the node to comeback
    set_node_ospf_link_cost_to_normal(nodes,selected_for_powerup,username,password)
    set_neighbour_nodes_ospf_link_cost_to_normal(nodes,selected_for_powerup,username, password)
    powerup_a_node_interfaces(nodes,selected_for_powerup,username, password)

def add_powered_up_node_to_current_edges(edge_list,powered_down_nodes):
    if powered_down_nodes:
        current_edges=edge_list
        for node in powered_down_nodes:
            current_edges=remove_node_from_graph(node,current_edges)
        return current_edges
    else:
        return edge_list
################################################################### MAIN STARTS ###########################################

if __name__=='__main__':
    #Run the Ansible playbook before this script
    try:
        #polling intervall
        freq=1
        #absolute path to the working directory 
        WORKING_DIR= '/home/botond/diplomatervezes2/'
        #other paths
        location_of_the_running_interfaces = WORKING_DIR+"interface_info"
        location_of_the_mgmt_and_access_csv = WORKING_DIR + "python_snmp/mgmt_and_access_networks.csv"
        location_of_the_managed_routers_csv = WORKING_DIR+'python_snmp/inventory.csv'
        location_of_logfile = WORKING_DIR+'python_snmp/log.txt'
        #Credentials for SSH command executions
        username="Boti"
        password="Halozat"
        #Check if the ansible playbook collected the neccesarry information from the nodes
        if  os.path.isdir(location_of_the_running_interfaces) == False:
            raise Exception("Please run the Ansible playbook first")
        if not os.listdir(location_of_the_running_interfaces):
            raise Exception("Please run the Ansible playbook first, the interface_info folder is empty")     
        #Setting up the nodes for monitoring
        nodes=create_node_instance(location_of_the_managed_routers_csv)
        for node in nodes:
            node.poll_basic_info()
            node.poll_interfaces()
            if node.name:
                print("\033[2;30;47mNode SNMP info:\033[0m",node.ip_address ,node.community_string, node.snmp_version)
                print("\033[2;30;47mThe device name is:\033[0m",node.name)
                print("\033[2;30;47mThe up interfaces:\033[0m")
                for item in node.only_up_physical_interfaces:
                    print(item.if_index, '-----', item.if_descr, '-----', item.if_speed, '-----', item.if_oper_status)
        append_interface_info(location_of_the_running_interfaces,nodes)
        extract_interface_info(nodes,location_of_the_mgmt_and_access_csv)
        print()
        edge_list=bulding_the_network_topology(nodes)
        print("These are the edges:",edge_list,"\n")
        nodes_with_access_interface=[]
        transport_nodes=[]
        for node in nodes:
            print(f" {node.name}'s neighbours:{node.neighbour_nodes}")
            if node.has_access_interface:
                nodes_with_access_interface.append(node.name)
            else:
                transport_nodes.append(node.name)
        print(f"\nThese are the nodes that have access interface: {nodes_with_access_interface}\nThese are the transport nodes: {transport_nodes}")  
        # Create a separate process to plot the graph
        graph_process = Process(target=plot_the_graph_of_nodes, args=(edge_list,nodes_with_access_interface))
        graph_process.start()
#################################### GLOBAL VARS ##########################
        current_edges=edge_list.copy()
        have_enough_data=False
        powered_down_nodes=[]
        can_remove_more_nodes=True
        candidates_for_powersave=[]
#############################################################################    
        #Monitoring the link utilizations 
        #print(\033[2;30;47mMonitoredNode.node_names\033[0m) 
        start_time=datetime.now()
        with open(location_of_logfile, 'a') as file:
            file.write("\n\n\n#####################################################################################################\nStart Time: " + start_time.strftime("%Y-%m-%d %H:%M:%S") + "\n")
        last_powerup_time = datetime.now()
        last_turnoff_time = datetime.now()
        last_traffic_poll=datetime.now()
        time.sleep(freq)
        print("\033[2;30;47mTraffic of the up interfaces:\033[0m")
        try:           
            while True:
                if datetime.now() -last_traffic_poll > timedelta(seconds=freq):
                    for node in nodes: 
                        poll_interface_traffic(node)
                        last_traffic_poll=datetime.now()  
                    if datetime.now() - start_time > timedelta(seconds=40):
                        print("Checking for powersave options")
                        print()
                        if have_enough_data == False:
                            print("Please wait, collecting more data...")
                            have_enough_data = check_if_there_are_enough_utilization_data(nodes,5) #2nd param is the number of utilization data needed for the program to start
                        else:
                            ############################ MAIN PROGRAM ########################################
    ##################################################### POWERUP CHECK ####################################################################################
                            if powered_down_nodes and datetime.now() - last_powerup_time > timedelta(seconds=10) and datetime.now() - last_turnoff_time > timedelta(seconds=10):
                                #will have to set can_remove_more_nodes to true if power up a node and remove it from powered_down_nodes
                                print("Checking for powerup\n")
                                #1 check if any link is above threshold
                                if is_any_link_above_a_threshold(nodes,80,2): #2nd param is the threshold in percentage the 3rd is for how many cycles
                                    #2 select shutdown node for powerup
                                    selected_for_powerup=select_candidate_for_powerup(nodes,powered_down_nodes,80) #3rd param is the threshold in percentage
                                    #3 powerup the node and set variables
                                    powerup_a_node(nodes,selected_for_powerup,username, password)
                                    print("Powerup successful")
                                    last_powerup_time = datetime.now()
                                    powered_down_nodes=[item for item in powered_down_nodes if item != selected_for_powerup] #remove powered up node from down nodes
                                    current_edges=add_powered_up_node_to_current_edges(edge_list,powered_down_nodes) #add node to edges 
                                    with open(location_of_logfile, 'a') as file:
                                        file.write("\n+Successfully powered up "+selected_for_powerup +" at "+ last_powerup_time.strftime("%Y-%m-%d %H:%M:%S")+ "\nThese are the current edges:\n"+ str(current_edges))
                                    can_remove_more_nodes=True
                                    print(f"These are the current edges {current_edges}")
    ##################################################### SUTDOWN CHECK ####################################################################################
                            if can_remove_more_nodes and datetime.now() - last_powerup_time > timedelta(seconds=40) and datetime.now() - last_turnoff_time > timedelta(seconds=30):
                                # will have to set can_remove_more_nodes to False if cannot remove and add the node to powered_down_nodes if powered down  
                                #1 check all transport nodes if they can be taken out of the graph if none can be taken out set can_remove_more_nodes to false
                                can_remove_more_nodes,candidates_for_powersave = check_if_any_node_can_be_removed(current_edges,nodes_with_access_interface,transport_nodes,powered_down_nodes)
                                if can_remove_more_nodes:
                                    print("Checking for shutdown:\n")
                                    if is_every_transport_link_under_x_utilization(nodes,50,3): #2nd parameter is the maximum link util and the 3rd param is how many cycles does it have to stay under to start the powersaving 
                                        #2 select candidate for shutdown
                                        if candidates_for_powersave:
                                            selected_for_shutdown=select_candidate_for_shutdown(nodes,candidates_for_powersave,2,30) #3rd param is for how many cycles the 4th is the threshold in percentage
                                        #3 shutdown and set variables  
                                        shutdown_node(nodes,selected_for_shutdown,username, password,time_between_cost_set_and_shutdown=20)
                                        print("Shutdown successful")
                                        last_turnoff_time = datetime.now()
                                        powered_down_nodes.append(selected_for_shutdown)
                                        current_edges=remove_node_from_graph(selected_for_shutdown,current_edges)
                                        with open(location_of_logfile, 'a') as file:
                                            file.write("\n-Successfully shutdown "+ selected_for_shutdown +" at "+ last_turnoff_time.strftime("%Y-%m-%d %H:%M:%S") + "\nThese are the current edges:\n"+ str(current_edges))
                                        print(f"These are the current edges {current_edges}")
                                    else:
                                        print("Cannot shutdown any node.\nThere are links above threshold in the given period.")
                        ############################ MAIN END ############################################
        except KeyboardInterrupt:
            graph_process.terminate()
            print('Program stopped by user')
        except Exception as e:
            print(f'Unexpected error happened {e}')

    except Exception as e:
        print(f'Unexpected error happened {e}')