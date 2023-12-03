import  time, paramiko 

username="Boti"
password="Halozat"
routers=['10.10.20.201','10.10.20.202','10.10.20.203','10.10.20.204','10.10.20.205','10.10.20.206','10.10.20.207','10.10.20.208']
int_ranges=['2-6','2-6','2-6','2-7','2-6','2-5','2-4','2-5']
int_index=0
for router in routers:
    
    try:
        ssh = paramiko.SSHClient()
                # Automatically add the server's host key
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
                    
        ssh.connect(router, username=username, password=password)
        print("Connected to the router.")

                # Start an interactive shell
        shell = ssh.invoke_shell()
        command="conf t\ninterface range gi"+int_ranges[int_index]+"\nno shut\nno ip ospf cost\n"
        shell.send(command + "\n")
        time.sleep(4)
        output = shell.recv(65535).decode()
        print(output)
        int_index+=1        

    except paramiko.AuthenticationException:
                print("Authentication failed. Please check the credentials.")
    except paramiko.SSHException as ssh_ex:
                print(f"Unable to establish SSH connection: {str(ssh_ex)}")
    except KeyboardInterrupt:
                print("Shutdown stopped by user.")
    finally:
            ssh.close()