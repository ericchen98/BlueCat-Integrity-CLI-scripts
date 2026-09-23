#!/usr/bin/python
# coding:utf-8
# vim: tabstop=8 expandtab shiftwidth=4 softtabstop=4
# Copyright 2017 BlueCat Networks. This software is released under an
# OSI-approved license, the Python Software License 2.0. This license is
# incorporated by reference. The license grants you certain rights.
#
# https://opensource.org/licenses/Python-2.0

# name: server-role.py - Note: this script is replaced by dnsRole_add.py & dnsRole_delete.py
#
#
# v3.3-20251228 add note about this prog is replaced by dnsRole_add.py & dnsRole_delete.py
# v3.2-20230828 fixed log does not show in cli.py issue 
# v3.1-2023-0827 - replace sys.exit() to return() (to work with cli.py)
#                - update help
# v3.0-20221226 (1) use BAM.py for log & process_password, create function server_role()
#               (2) change log dir to "./"
#               (3) add the code to support converting serverName to lower case if convertServer =True
#                   but didn't enable it (set convertServer=False)
# v2.2 2020/5/26 read config file from dir: /opt/bluecat/cli
# v2.1 2020/5/6 change argument - add -a (add) -d (delete) -r (role) etc.
# v2.0 add log support
# v1.1.3
#   2019/12/12 Eric: rename this script from "bam-1.1.2.py" to server-role.py
#   Eric 2018 : add/del BDDS dploy role to  view/zone
# V1.1.2
#   server-role.pye takes a BDDS servername and a zone / view to be assigned to as a DNS master/ slave role.
#   Edit bamconfig.json to have the appropriate values for your configuration.
#   The program has three switches and two parameter
#
# Note: "-d" is used for debug. Cannot be used as "delete" (use -x instead)
#

"""
server-role -c config_name -v view_name [-a|-x] -r [master|slave] -s server_name
 
server-role -c config1 -v view1              -a -r master -s dds1 (Add "dds1" as master of view "view1")
server-role -c config1 -v view1 -z test.corp -a -r master -s dds1 (Add "dds1" as master of zone "test.corp")
server-role -c config1 -v view1 -z test.corp -a -r slave  -s dds2 (Add "dds2" as slave  of zone "test.corp")
server-role -c config1 -v view1 -z test.corp -x           -s dds1 (delete "dds1" role from zone test.corp)

    -c config  the configuration into which these changes should be made (bamconfig has a default)
    -v view    the view name mandatory
    -z zone    the zone name to which the DNS role needs to be assigned
    -a         add role
    -x         delete existing role
    -r role    DNS deploy role ("MASTER","SLAVE","RECURSION", "FORWARDER", "STUB","NONE", 
                                "MASTER_HIDDEN" ,"SLAVE_STEALTH" ,"AD_MASTER")
    -s name    the BDDS server name

    # add/delete server deploy roles to a view/zone
    Note: this script is replaced by dnsRole_add.py and dnsRole_delete.py
"""

import getopt
import sys
import json
import os

import BAM

# ---------------------------------------------------------------------
# New module to replace BAM (zeep, SOAP)
# ---------------------------------------------------------------------
# suppress InsecureRequestWarning for zeep when set "websession.verify = False"
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ---------------------------------------------------------------------
# global var
# ---------------------------------------------------------------------

version = "3.3"

# to disable exception trackback information (if not set, urllib3 excpetion will be printed to screen)
#sys.tracebacklimit = 0

#-------------------------------------------
# working & log path setup (Win & Linux)
#-------------------------------------------
win_workingDir = "./"
win_logPath = "./"
win_logFileName = "cli"
Linux_workingDir =  "./"
Linux_logPath =  "./"
Linux_logFileName = "cli"

#-------------------------------------------
# convertServer = True | False //whether to convert dds name
#-------------------------------------------

# Note found cannot do convert if user add upper case server name in GUI, the dds cannot be deleted
convertServer = False

# ---------------------------------------------------------------------
# main function
# ---------------------------------------------------------------------
def server_role(*args):    

    # ---------------------------------------------------------------------
    # local #def
    # ---------------------------------------------------------------------
    # define log_prog_type_index : to be called in BAM.print_log()
    prog_type_view = 0
    prog_type_add = 1
    prog_type_delete = 2
    prog_type_update = 3
    prog_type_other = 4

    # set log_prog_type_index by script type (view, add, delete etc.) will print eg "view" in log
    log_prog_type_index = prog_type_add

    # log_info_error = 0(info), 1(error). This is used to call bam.print_log()
    log_info = 0
    log_error = 1

    # default = 3 sec. If change any  other number, it will overwrite 
    #       REST requests timeout value
    req_timeout = 5

    # read max obj count in API
    max_obj_count = "1000"
    
    role_type_supported=[ "AD_MASTER", "FORWARDER", "MASTER" ,"MASTER_HIDDEN" ,
        "NONE" ,"RECURSION" ,"SLAVE" ,"SLAVE_STEALTH" ,"STUB"]

    # ---------------------------------------------------------------------
    # local var 
    # ---------------------------------------------------------------------
    logMsg = ''
    input_cmd_log = ''
    
    api = ''
    apiPw = ''
    apiPw_decode = ''
    https = False

    configuration = None
    view = None
    zone = None
    show_version = False

    #---------------------------- var to check
    roletype = None
    servername = None
    delete = False
    add = False

    noisy = True
    doit = True
    debug = False

    confid = 0
    viewid = 0
    zoneid = 0
    parentid = 0
    
    log_type_add = False        # to add operation type "add" to log
    log_type_delete = False     # to add operation type "delete" to log

    # ------------------------------------------ for debug
    debug = False           # -d of getopt() 
    debug_input = None      # input (type str) of getopt()
    debug_user = False
    debug_api  = False
    debug_bam  = False
    
    # ------ set up program home dir for Win & Linux ------
    workingDir = ''
    logPath = ''
    logFileName = ''
    if os.name == 'nt':
        #  same dir in Windows
        workingDir = win_workingDir
        logPath = win_logPath
        logFileName = win_logFileName
    else:
        # Linux platform
        workingDir = Linux_workingDir
        logPath = Linux_logPath
        logFileName = Linux_logFileName
        
    # BAM.get_input_cmd() is a function. 
    #----------------------------------------------------------------
    #fixed log input issue when called by cli.py or python3 xxx.py
    #----------------------------------------------------------------
    #get program name. If prog is called by cli.py, then __name__ will be "a_query"
    prog_name = __name__
    
    #convert "_" to "-" in prog_name
    prog_name = prog_name.replace('_','-')
    
    if __name__ == '__main__': #this program is run by python directly (e.g. python3 a_query.py)
         #will get user full input commands and remove ".py"
        input_cmd_log = BAM.get_input_cmd()
    else: #this program is called by cli.py (use args as log output file)
        input_cmd_log_from_args = ' '.join(args)
        input_cmd_log = " Input: %s %s" % (prog_name,input_cmd_log_from_args)
    
    # will create a logger, store input_cmd_log and setup logpath logFileName to logger
    # 2022-12-26 10:26:35,eric,vDNS,,cli,Add<---,"[ERROR]:Failure:
    print_log = BAM.print_log( log_prog_type_index ,input_cmd_log, logPath, logFileName)
    
    # print_log_del will create "2022-12-26 10:26:49,eric,vDNS,,cli,Delete<---,"[ERROR]:Failure:"
    print_log_del = BAM.print_log( prog_type_delete ,input_cmd_log, logPath, logFileName)

    #-------------------------------------------------------------------
    # load config by BAM.load_config()  return json format "config"
    #-------------------------------------------------------------------
    configFile = workingDir + "bamconfig.json"
    config = BAM.load_config(print_log, configFile)

    if config['https'].upper() == 'TRUE':
        https = True
    else:
        https = False

    # --- get api & apiPw ---
    api = config['user']
    apiPw = config['password'] 
    
    # decode api verify encrypted password to see if it is valid.
    apiPw_decode = BAM.decrypt_password(apiPw) 
        
    if apiPw_decode == '':
        logMsg = "API user password decode error"
        print_log.go(log_error, logMsg)
        return(1)  
    # ---------------------------------------------------------
    # read from CLI
    # ---------------------------------------------------------
    input_args = list(args)   # args is the arguments passed by calling this function.
    try:
        # this is to prepare if this script is called by other python script.
        if len(input_args)!=0:    #this is called by other python script
            opts, args = getopt.getopt(  input_args, "qndc:v:z:axr:s:h", ["debug=","version"])           
        else: # call this script from CLI. Parsing "sys.argv[1:]" ([1:] - not include script name)
            opts, args = getopt.getopt(sys.argv[1:], "qndc:v:z:axr:s:h", ["debug=","version"])
    except getopt.GetoptError as e: 
        logMsg = str(e)
        print_log.go(log_error, logMsg)
        return(1) 


    for o,v in opts:
        if o == "-q": noisy = False     # func disabled 
        elif o == "-n": doit = False    # func disabled 
        elif o == "-d": debug = True 
        elif o == "-c": configuration = v
        elif o == "-v": view = v
        elif o == "-z": zone = v
        elif o == "-a": add = True
        elif o == "-x": delete = True
        elif o == "-r": roletype = v
        elif o == "-s": servername = v
        elif o == "--version": show_version = True
        elif o == "--debug": debug_input = v  
        elif o == "-h":
            print (__doc__)
            return (0)

    if not opts:
        print (__doc__)
        return (0)

    # roletype needs to be upper case.
    if roletype:
        roletype = roletype.upper()
        # check if roletype valid
        if not roletype in role_type_supported:
            logMsg = "Failure: -r role is invalid"
            print_log.go(log_error, logMsg) if log_type_add else print_log_del.go(log_error, logMsg)
            return(1)
            
    if show_version == True:
        print("Version %s" % version)
        return(0)

    if doit:
        no = ""
    else:
        no = "(dry run) NOT"

    # ---------------------------------------------------------
    # debug setup
    # ---------------------------------------------------------
    if debug:
        debug_user = True    # value 1
        debug_api = False 
        debug_bam = False 
    if debug_input == 'api':
        sys.tracebacklimit = 1000   # turn on tracking
        debug_user = True
        debug_api = True 
        debug_bam = False 
    elif debug_input == 'bam':
        sys.tracebacklimit = 1000   # turn on tracking
        debug_user = True
        debug_api = True 
        debug_bam = True 

    # ---------------------------------------------------------
    # test cli required parameters 
    # ---------------------------------------------------------
    
    if add and delete: # add and delete cannot exist at the same time
        logMsg = "Failure: -a (add) and -x (delete) cannot exist at the same time"
        print_log.go(log_error, logMsg)
        return(1)
    else:
        if add:
            log_type_add = True
        else:
            # delete is true:
            log_type_delete = True  # (this var won't be used. if log_type_add = T, it is add (else delete).

    # -a or -x must have
    if not (add or delete):
        logMsg = "Failure: -a or -d option is required"
        print_log.go(log_error, logMsg) if log_type_add else print_log_del.go(log_error, logMsg)
        return(1)
    
    if (not configuration) or (configuration[0:1] == "-"):
        logMsg = "Failure: -c config option is required"
        print_log.go(log_error, logMsg) if log_type_add else print_log_del.go(log_error, logMsg)
        return(1)

    if (not view) or (view[0:1] == "-"):
        logMsg = "Failure: -v view option is required"
        print_log.go(log_error, logMsg) if log_type_add else print_log_del.go(log_error, logMsg)
        return(1)
    if zone != None:    
        if (zone[0:1] == "-"):
            logMsg = "Failure: -z parameter error"
            print_log.go(log_error, logMsg) if log_type_add else print_log_del.go(log_error, logMsg)
            return(1)
    
    
    if not delete:  # if no -x: roletype is required (delete does not need -r role type). 
        # roletype and servername must have
        if (not roletype) or (roletype[0:1] == "-"):
            logMsg = "Failure: -r role option is required"
            print_log.go(log_error, logMsg) if log_type_add else print_log_del.go(log_error, logMsg)
            return(1)

    if (not servername) or (servername[0:1] == "-"):
        logMsg = "Failure: -s servername option is required"
        print_log.go(log_error, logMsg) if log_type_add else print_log_del.go(log_error, logMsg)
        return(1)
        
    if convertServer: #convert servername to lower case
        if not (servername == None):
            servername = servername.lower()
        
    # ----------------------------------------------------------------
    # login to BAM
    # ----------------------------------------------------------------
    if https:
        BAM_URL = "https://" + config['hostname'] + "/Services/REST/v1/"
    else:
        BAM_URL = "http://" + config['hostname'] + "/Services/REST/v1/"       
    try:                   
        bam=BAM.BAM( BAM_URL, req_timeout)       
        response = bam.login( api, apiPw_decode )   #response.ok is checked in bam.login()
    except Exception as e:  # except of login()
        logMsg = bam.mask_id_pw( str(e) )   # mask username and pw in e when login fail
        print_log.go(log_error, logMsg) if log_type_add else print_log_del.go(log_error, logMsg)
        return(1)    

    # ----------------------------------------------------------------
    # get config/view/zone
    # ----------------------------------------------------------------
    err_msg = ''
    if configuration:
        config_ent = bam.getEntityByName("0", configuration, "Configuration")
        confid = config_ent['id']
        if confid == 0:
            logMsg = "Failure: Failed to get configuration: %s" % (configuration)
            print_log.go(log_error, logMsg) if log_type_add else print_log_del.go(log_error, logMsg)
            BAM.bam_logout(bam)
            return(1)
        if view:
            view_ent = bam.getEntityByName(confid, view, "View")
            viewid = view_ent['id']
            if viewid == 0:
                logMsg = "Failure: Failed to get view: %s" % (view)
                print_log.go(log_error, logMsg) if log_type_add else print_log_del.go(log_error, logMsg)
                BAM.bam_logout(bam)
                return(1)
            else:    
                parentid = viewid
            

            if zone:
                zone_ent = bam.find_zone(viewid, zone)
                zoneid = zone_ent['id']
                if zoneid == 0:
                    logMsg = "Failure: Failed to get zone: %s" % (zone)
                    print_log.go(log_error, logMsg) if log_type_add else print_log_del.go(log_error, logMsg)
                    BAM.bam_logout(bam)
                    return(1)
                else:
                    parentid = zoneid
                 
                # ------------------------------------------------ 
                # End of read config/view/zone 
                # ------------------------------------------------ 
            #endof if zone:
        # endof if view:
        
        # "parentid" is set as viewid or zoneid
        
        # Get Server hostname
        try:
            s = bam.getEntityByName(confid, servername, "Server")
            serverid = s['id']    
        except ValueError as e:
            logMsg = "Failure: %s Failed to get Server: %s" % (str(e),servername)
            print_log.go(log_error, logMsg) if log_type_add else print_log_del.go(log_error, logMsg)
            BAM.bam_logout(bam)
            return(1)
            
        if serverid == 0:
            logMsg = "Failure: Failed to get Server: %s" % servername
            print_log.go(log_error, logMsg) if log_type_add else print_log_del.go(log_error, logMsg)
            BAM.bam_logout(bam)
            return(1)

        properties = bam.splitProp(s)
        fullhostname = properties['fullHostName']

        try:
            sif = bam.getEntityByName(serverid, fullhostname, "NetworkServerInterface")
            sifid = sif['id']
        except ValueError as e:
            logMsg = "Failure: %s Network interface for server %s is unknown" % (str(e), servername)
            print_log.go(log_error, logMsg) if log_type_add else print_log_del.go(log_error, logMsg)
            return(1)
                
        if sifid == 0:
            logMsg = "Failure: Failed to get Network interface for server %s" % servername
            print_log.go(log_error, logMsg) if log_type_add else print_log_del.go(log_error, logMsg)
            BAM.bam_logout(bam)
            return(1)
        
        if delete:
            try:
                retval = bam.deleteDNSDeploymentRole(parentid, sifid)
                print
                logMsg =  "Success: Deleted server %s role from view/zone" % (servername)
                print_log.go(log_info, logMsg) if log_type_add else print_log_del.go(log_info, logMsg)
                BAM.bam_logout(bam)
            except ValueError as e:
                logMsg = "Failure: %s Failed to delete DNS Deployment role on server %s" % (str(e), servername)
                print_log.go(log_error, logMsg) if log_type_add else print_log_del.go(log_error, logMsg)
                BAM.bam_logout(bam)
                return(1)
                
        if add:    # Add DNS deployment role here
            try:
                retval = bam.addDNSDeploymentRole(parentid, sifid, roletype, "")
                logMsg =  "Success: Added server %s as %s on view/zone" % (servername, roletype)
                print_log.go(log_info, logMsg) if log_type_add else print_log_del.go(log_info, logMsg)
                BAM.bam_logout(bam)
            except ValueError as e:
                logMsg = "Failure: %s Failed to add DNS Deployment role %s on server %s" % (str(e), roletype, servername)
                print_log.go(log_error, logMsg) if log_type_add else print_log_del.go(log_error, logMsg)
                BAM.bam_logout(bam)
                return(1)
        
    #endof if configuration:
#endof def server_role(*args):

# ---------------------------------------------------------------------
# main()
# ---------------------------------------------------------------------
if __name__ == '__main__':
    server_role()

