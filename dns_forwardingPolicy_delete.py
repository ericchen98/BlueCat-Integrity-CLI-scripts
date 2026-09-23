#!/usr/bin/python3
# coding:utf-8
#
# Copyright 2021 BlueCat Networks. This software is released under an
# OSI-approved license, the Python Software License 2.0. This license is
# incorporated by reference. The license grants you certain rights.
# https://opensource.org/licenses/Python-2.0
#
# Bluecat only provides this Script for reference as a Proof of Concept
#
# by: Eric Chen (hchen@bluecatnetworks.com)
# python ver: python 3
#
# v1.0-20260712 create


"""
dns_forwardingPolicy_delete -c config1 -v view1 -s dds1
    -c config_name
    -v view_name
    -s dds_server 
    -g server_group
    -y                 # add option to server or serverGroup instead of configuration
    
dns_forwardingPolicy_delete -c config1                     # delete policy from config1
dns_forwardingPolicy_delete -c config1 -v view1            # delete policy from view1 in config1
dns_forwardingPolicy_delete -c config1 -v view1 -s dds1    # delete policy from dds1 in view1
dns_forwardingPolicy_delete -c config1 -v view1 -g sg1     # delete policy from serverGroup sg1 in view1
dns_forwardingPolicy_delete -c config1          -s dds1    # delete policy from dds1 in config1
dns_forwardingPolicy_delete -c config1          -g sg1     # delete policy from serverGroup sg1 in config1
dns_forwardingPolicy_delete -c config1          -s dds1 -y # delete policy from server dds1
dns_forwardingPolicy_delete -c config1          -g sg1  -y # delete policy from serverGroup sg1
"""

import getopt
import sys
import json
import os

# ---- test commands (add & delete)
'''
python dns_forwardingPolicy_add.py    -c config1 -o
python dns_forwardingPolicy_delete.py -c config1

python dns_forwardingPolicy_add.py y -c config1 -v view1 -o
python dns_forwardingPolicy_delete.p -c config1 -v view1

python dns_forwardingPolicy_add.py y -c config1 -v view1 -s dds1 -o
python dns_forwardingPolicy_delete.p -c config1 -v view1 -s dds1

python dns_forwardingPolicy_add.py y -c config1 -v view1 -g sg1 -o
python dns_forwardingPolicy_delete.p -c config1 -v view1 -g sg1

python dns_forwardingPolicy_add.py y -c config1 -s dds1 -o 
python dns_forwardingPolicy_delete.p -c config1 -s dds1

python dns_forwardingPolicy_add.py y -c config1 -g sg1 -o 
python dns_forwardingPolicy_delete.p -c config1 -g sg11

python dns_forwardingPolicy_add.py y -c config1 -s dds1 -y -o 
python dns_forwardingPolicy_delete.p -c config1 -s dds1 -y

python dns_forwardingPolicy_add.py y -c config1 -g sg1 -y -o 
python dns_forwardingPolicy_delete.p -c config1 -g sg1 -y
'''

# ------------- module by BlueCat ---------
import BAM

# ---------------------------------------------------------------------
# New module to replace BAM (zeep, SOAP)
# ---------------------------------------------------------------------
# suppress InsecureRequestWarning for zeep when set "websession.verify = False"
import urllib3  # to suppress https cert worning
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ---------------------------------------------------------------------
# global var
# ---------------------------------------------------------------------

version = "1.0"

# to disable exception trackback information (if not set, urllib3 excpetion will be printed to screen)
sys.tracebacklimit = 0

# ---------------------------------------------------------------------
# main function
# ---------------------------------------------------------------------
def dns_forwardingPolicy_delete(*args):    

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

    # log_info_error = 0(info), 1(error). This is used tl call bam.print_log()
    log_info = 0
    log_error = 1

    # default = 3 sec. If change any  other number, it will overwrite 
    #       REST requests timeout value
    req_timeout = 5

    # read max obj count in API
    max_obj_count = "1000"

    # ---------------------------------------------------------------------
    # local var 
    # ---------------------------------------------------------------------
    logMsg = ''
    cmdLine = ''
    input_cmd = ''
    input_cmd_log = ''
    
    api = ''
    apiPw = ''
    apiPw_decode = ''
    https = False

    configuration = ''
    view = ''
    server = ''
    
    zone = None
    rrName = None
    rdata = None
    matchclient = None
    user = None
    show_version = False

    confid = 0
    viewid = 0
    zoneid = 0

    server_id = 0
    server = ''
    server_name = ''
    serverGroup = ''

    forwardingIP = ''
    diable_fwd_child_zone = ''
    forward_config = ''

    add_to_server_input = False


    addrList = []
    ip_match = False
    index = 0
    addptr= False
    propertiesString = ''

    debug_level=0
    debug1=False
    debug2=False

    foo1=None
    addrList_sort =''

    
    do_config = False
    do_view = False
    do_server = False
    
    do_success = False
    
    # ------------------------------------------ for debug
    debug = False           # -d of getopt() 
    debug_input = None      # input (type str) of getopt()
    debug_user = False
    debug_api  = False
    debug_bam  = False
    # ------ set up program home dir for Win & Linux ------
    workingDir = ''
    if os.name == 'nt':
        #  same dir in Windows
        workingDir = "./"
        logPath = "./"
        logFileName = "cli"
    else:
        # Linux platform
        workingDir = "./"
        logPath = "./"
        logFileName = "cli"
        
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
    print_log = BAM.print_log( log_prog_type_index ,input_cmd_log, logPath, logFileName)

    #-------------------------------------------------------------------
    # load config by BAM.load_config()  return json format "config"
    #-------------------------------------------------------------------
    configFile = workingDir + "bamconfig.json"
    config = BAM.load_config(print_log, configFile)

    if config['https'].upper() == 'YES':
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
            opts, args = getopt.getopt(  input_args, "dc:v:s:g:yh", ["debug=","version"])
        else: # call this script from CLI. Parsing "sys.argv[1:]" ([1:] - not include script name)
            opts, args = getopt.getopt(sys.argv[1:], "dc:v:s:g:yh", ["debug=","version"])
    except getopt.GetoptError as e: 
        logMsg = str(e)
        print_log.go(log_error, logMsg)
        return(1) 

    for o,v in opts:
        if o == "-d": debug = True 
        elif o == "-c": configuration = v
        elif o == "-v": view = v
        elif o == "-s": server = v
        elif o == "-g": serverGroup = v
        elif o == "-y": add_to_server_input = True
        elif o == "--version": show_version = True
        elif o == "--debug": debug_input = v  
        elif o == "-h":
            print (__doc__)
            return(0)
    if not opts:
        print (__doc__)
        return(0)
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
    
    if debug_api: 
        print('[debug: ------- print input parameter-------]')
        print(opts)
    if show_version == True:
        print("Version %s" % version)
        return(0)
    
    if (not configuration) or (configuration[0:1] == "-"):
        logMsg = "Failure: -c configuration option is required"
        print_log.go(log_error, logMsg)
        return (1)
    
    # ---------------------------------------------------------
    # test cli parameters 
    # ---------------------------------------------------------
    do_config = False
    do_view = False
    do_server = False
    do_serverGroup = False
    

    if (configuration) and (configuration[0:1] != "-"): # config set
        do_config = True
    if (view) and (view[0:1] != "-"): #view set
        do_view = True
    if (server) and (server[0:1] != "-"): #server set
        do_server = True
    if (serverGroup) and (serverGroup[0:1] != "-"): #server set
        do_serverGroup = True      # do server under view

    # --- if both -s and -g exist, use '-s' only
    if do_server and do_serverGroup:
        do_server = True
        do_serverGroup = False

    # --- parameter test and debug ---
    '''
    print( "do_config", do_config )
    print( "do_view ", do_view )
    print( "do_server", do_server )
    print( "do_serverGroup", do_serverGroup )
    print('-------------------------------------')
    '''
    
    do_config_go = False
    do_view_go = False
    do_view_server_go = False
    do_view_serverGroup_go = False
    do_config_server_go = False
    do_config_serverGroup_go = False
    do_server_go = False
    do_serverGroup_go = False

    
    if do_config and (not do_view) and (not do_server) and (not do_serverGroup):
        do_config_go = True
    elif (do_view) and (not do_server) and (not do_serverGroup):
        do_view_go = True
    elif (do_view) and (do_server) and (not do_serverGroup):
        do_view_server_go = True
    elif (do_view) and (do_serverGroup):
        do_view_serverGroup_go = True
    elif do_config and (not do_view) and (do_server) and (not do_serverGroup):
        if add_to_server_input:
            do_server_go = True
        else:
            do_config_server_go = True
    elif do_config and (not do_view) and (not do_server) and (do_serverGroup):
        if add_to_server_input:
            do_serverGroup_go = True
        else:
            do_config_serverGroup_go = True
    
    # --- for debug parameter input debug ---
    '''
    print ('do_config_go', do_config_go)
    print('do_view_go', do_view_go)
    print('do_view_server_go', do_view_server_go)
    print('do_view_serverGroup_go', do_view_serverGroup_go)
    print('do_config_server_go', do_config_server_go)
    print('do_config_serverGroup_go', do_config_serverGroup_go)
    print('do_server_go', do_server_go)
    print('do_serverGroup_go', do_serverGroup_go)
    print('add_to_server_input', add_to_server_input)
    return
    '''
    
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
        print_log.go(log_error, logMsg)
        return(1)    
    # ----------------------------------------------------------------
    # Start to get data from BAM
    # ----------------------------------------------------------------
    err_msg = ''
       
    try:
        if configuration:
            config_ent = bam.getEntityByName("0", configuration, "Configuration")
            confid = config_ent['id']
            if confid == 0:
                logMsg = "Failure: Failed to get configuration: %s" % (configuration)
                print_log.go(log_error, logMsg)
                BAM.bam_logout(bam)
                return (1)
                
        if do_config_go: # add option to config
            # -----------------------------------------------------------------
            # add option to config
            # python dns_forwardingPolicy_add.py    -c config1 -o
            # python dns_forwardingPolicy_delete.py -c config1
            # -----------------------------------------------------------------
            try:
                ent = bam.getDNSDeploymentOption(confid, "forwarding-policy", "0")
                if debug_api:
                    print('[debug: ------- search result of getDNSDeploymentOption() -------]')
                    print(ent)
                
            except ValueError as e:
                    logMsg = "Failure: %s Failed to search DNS forwarding option" % ( str(e) )
                    print_log.go(log_error, logMsg)
                    BAM.bam_logout(bam)
                    return(1)
            
            if ent['id']== 0:
                logMsg = 'Failure: DNS forwarding option of config:"%s" does not exist' % (configuration)
                print_log.go(log_error, logMsg)
                BAM.bam_logout(bam)
                return(1)
            
            else: #found option, get value and delete it
            
                value = ent['value']

                try:
                    bam.deleteDNSDeploymentOption(confid, "forwarding-policy", "0")
                except ValueError as e:
                        logMsg = "Failure: %s Failed to delete DNS forwarding option" % ( str(e) )
                        print_log.go(log_error, logMsg)
                        BAM.bam_logout(bam)
                        return(1)
                else:
                    logMsg =  ('Success: delete DNS forwarding-policy option:"%s" '
                                'in config:"%s"') % (value, configuration )
                                                        
                    print_log.go(log_info, logMsg)
                    BAM.bam_logout(bam)
                    return(0)
                
        elif do_view_server_go: # add option to server under view(do_view=T, do_server=T)
            # -----------------------------------------------------------------
            # add option to server under view 
            # python dns_forwardingPolicy_add.py    -c config1 -v view1 -s dds1 -o
            # python dns_forwardingPolicy_delete.py -c config1 -v view1 -s dds1
            # -----------------------------------------------------------------
            if view:
                view_ent = bam.getEntityByName(confid, view, "View")
                viewid = view_ent['id']
                if viewid == 0:
                    logMsg = "Failure: Failed to get view: %s" % (view)
                    print_log.go(log_error, logMsg)
                    BAM.bam_logout(bam)
                    return(1)
                # ------------------------------------------------ 
                # get servers in configid 
                # ------------------------------------------------ 
                try:
                    result_list = bam.getEntities(confid, "Server", 0, max_obj_count)
                    
                    # server group
                    # result_list = bam.getEntities(confid, "ServerGroup", 0, max_obj_count)
                    
                except ValueError as e:
                    logMsg = "Failure: %s Failed to get server: %s" % (str(e), server)
                    print_log.go(log_error, logMsg)
                    BAM.bam_logout(bam)
                    return(1)
                
                do_success = False
                
                if debug_api:
                    print('[debug: ------- print search result of search server -------]')
                    print(result_list)
                
                for ent in result_list:

                    properties = bam.splitProp(ent)
                    server_id = ent['id']
                    server_name = ent['name']
                    
                    if server.upper() ==  server_name.upper(): # --- found target server to add
                        try:
                            ent = bam.getDNSDeploymentOption(viewid, "forwarding-policy", server_id)
                                                        
                            if debug_api:
                                print('[debug: ------- search result of getDNSDeploymentOption() -------]')
                                print(ent)
                            
                        except ValueError as e:
                                logMsg = "Failure: %s Failed to search DNS forwarding-policy option" % ( str(e) )
                                print_log.go(log_error, logMsg)
                                BAM.bam_logout(bam)
                                return(1)
                        
                        if ent['id']== 0:
                            logMsg = ('Failure: DNS forwarding-policy option of server:"%s" in view:"%s" '
                                      'does not exist') % (server, view)
                            print_log.go(log_error, logMsg)
                            BAM.bam_logout(bam)
                            return(1)
                        
                        else: #found option, get value and delete it
                            value = ent['value']
                            try:
                                bam.deleteDNSDeploymentOption(viewid, "forwarding-policy", server_id)
                                do_success = True
                            except ValueError as e:
                                    logMsg = "Failure: %s Failed to delete DNS forwarding-policy option" % ( str(e) )
                                    print_log.go(log_error, logMsg)
                                    BAM.bam_logout(bam)
                                    return(1)
                            else:
                                logMsg =  ('Success: delete DNS forwarding-policy option:"%s" '
                                  ' server:"%s" in view:"%s"') % (
                                  value, server, view)

                                print_log.go(log_info, logMsg)
                                BAM.bam_logout(bam)
                                return(0)
                        break
                        
                # end of for ent in result_list:
                # could be not found - break to here in for loop
                
                if not do_success:
                    logMsg = 'Failure: -s "%s" server name not found' % server
                    print_log.go(log_error, logMsg)
                    BAM.bam_logout(bam)
                    return (1)
                    
        elif do_view_serverGroup_go: 
            # -----------------------------------------------------------------
            # add option to serverGroup under view
            # python dns_forwardingPolicy_add.py    -c config1 -v view1 -g sg1 -o
            # python dns_forwardingPolicy_delete.py -c config1 -v view1 -g sg1
            # -----------------------------------------------------------------
            if view:
                view_ent = bam.getEntityByName(confid, view, "View")
                viewid = view_ent['id']
                if viewid == 0:
                    logMsg = "Failure: Failed to get view: %s" % (view)
                    print_log.go(log_error, logMsg)
                    BAM.bam_logout(bam)
                    return(1)
                # ------------------------------------------------ 
                # get servers in configid 
                # ------------------------------------------------ 
                try:
                    result_list = bam.getEntities(confid, "ServerGroup", 0, max_obj_count)
                    
                except ValueError as e:
                    logMsg = 'Failure: %s Failed to get serverGroup:"%s"' % (str(e), serverGroup)
                    print_log.go(log_error, logMsg)
                    BAM.bam_logout(bam)
                    return(1)
                
                do_success = False
                
                for ent in result_list:

                    properties = bam.splitProp(ent)
                    serverGroup_id = ent['id']
                    serverGroup_name = ent['name']
                                        
                    if serverGroup.upper() ==  serverGroup_name.upper(): # --- found target server to add
                        try:
                            ent = bam.getDNSDeploymentOption(viewid, "forwarding-policy", serverGroup_id)
                            if debug_api:
                                print('[debug: ------- search result of getDNSDeploymentOption() -------]')
                                print(ent)
                            
                        except ValueError as e:
                                logMsg = "Failure: %s Failed to search DNS forwarding-policy option" % ( str(e) )
                                print_log.go(log_error, logMsg)
                                BAM.bam_logout(bam)
                                return(1)
                        
                        if ent['id']== 0:
                            logMsg = ('Failure: DNS forwarding-policy option of serverGroup:"%s" '
                                      'in view:"%s" does not exist') % (serverGroup, view)
                            print_log.go(log_error, logMsg)
                            BAM.bam_logout(bam)
                            return(1)
                        
                        else: #found option, get value and delete it
                        
                            value = ent['value']
                        
                            try:
                                bam.deleteDNSDeploymentOption(viewid, "forwarding-policy", serverGroup_id)
                                do_success = True
                            except ValueError as e:
                                    logMsg = "Failure: %s Failed to delete DNS forwarding-policy option" % ( str(e) )
                                    print_log.go(log_error, logMsg)
                                    BAM.bam_logout(bam)
                                    return(1)
                            else:
                                logMsg =  ('Success: delete DNS forwarding-policy option:"%s" '
                                    'serverGroup:"%s" in view:"%s"') % (
                                    value, serverGroup, view)
                                print_log.go(log_info, logMsg)
                                BAM.bam_logout(bam)
                                return(0)
                        break
                        
                # end of for ent in result_list:
                # could be not found - break to here in for loop
                
                if not do_success:
                    logMsg = 'Failure: -s "%s" serverGroup name not found' % serverGroup
                    print_log.go(log_error, logMsg)
                    BAM.bam_logout(bam)
                    return (1)
            
        elif do_view_go: # add option to view only 
            # -----------------------------------------------------------------
            # add option to [view only] 
            # python dns_forwardingPolicy_add.py    -c config1 -v view1 -o
            # python dns_forwardingPolicy_delete.py -c config1 -v view1
            # -----------------------------------------------------------------
            view_ent = bam.getEntityByName(confid, view, "View")
            viewid = view_ent['id']
            
            if viewid == 0:
                logMsg = "Failure: Failed to get view: %s" % (view)
                print_log.go(log_error, logMsg)
                BAM.bam_logout(bam)
                return(1)
                
            else:    
                try:
                    ent = bam.getDNSDeploymentOption(viewid, "forwarding-policy", "0")
                    if debug_api:
                        print('[debug: ------- search result of getDNSDeploymentOption() -------]')
                        print(ent)
                    
                except ValueError as e:
                        logMsg = "Failure: %s Failed to search DNS forwarding-policy option" % ( str(e) )
                        print_log.go(log_error, logMsg)
                        BAM.bam_logout(bam)
                        return(1)
                
                if ent['id']== 0:
                    logMsg = 'Failure: DNS forwarding-policy option of config:"%s" does not exist' % (view)
                    print_log.go(log_error, logMsg)
                    BAM.bam_logout(bam)
                    return(1)
                
                else: #found option, get value and delete it
                    value = ent['value']

                    try:
                        bam.deleteDNSDeploymentOption(viewid, "forwarding-policy", "0")
                    except ValueError as e:
                            logMsg = "Failure: %s Failed to delete DNS forwarding-policy option" % ( str(e) )
                            print_log.go(log_error, logMsg)
                            BAM.bam_logout(bam)
                            return(1)
                    else:
                        logMsg =  ('Success: delete DNS forwarding-policy option:"%s" in view:"%s"') % (
                                  value, view )
                                                            
                        print_log.go(log_info, logMsg)
                        BAM.bam_logout(bam)
                        return(0)
                      
        elif do_config_server_go : #  add option [to server only]
            # -----------------------------------------------------------------
            # add option to server under config
            # python dns_forwardingPolicy_add.py    -c config1 -s dds1 -o 
            # python dns_forwardingPolicy_delete.py -c config1 -s dds1
            # -----------------------------------------------------------------
            
            # --- get servers in configid ---
            try:
                result_list = bam.getEntities(confid, "Server", 0, max_obj_count)
                
            except ValueError as e:
                logMsg = "Failure: %s Failed to get server: %s" % (str(e), server)
                print_log.go(log_error, logMsg)
                BAM.bam_logout(bam)
                return(1)

            if debug_api:
                print('[debug: ------- print all servers in config -------]')
                for ent in result_list:
                    print (ent)

            do_success = False
            
            for ent in result_list:

                properties = bam.splitProp(ent)
                server_id = ent['id']
                server_name = ent['name']
                
                if server.upper() ==  server_name.upper(): # --- found target server to add
                    try:
                        ent = bam.getDNSDeploymentOption(confid, "forwarding-policy", server_id)
                        if debug_api:
                            print('[debug: ------- search result of getDNSDeploymentOption() -------]')
                            print(ent)
                        
                    except ValueError as e:
                            logMsg = "Failure: %s Failed to search DNS forwarding-policy option" % ( str(e) )
                            print_log.go(log_error, logMsg)
                            BAM.bam_logout(bam)
                            return(1)
                        
                    if ent['id']== 0:
                        logMsg = ('Failure: DNS forwarding-policy option of server:"%s" in config:"%s" '
                                 'does not exist') % (server, configuration)
                        print_log.go(log_error, logMsg)
                        BAM.bam_logout(bam)
                        return(1)
                    
                    else: #found option, get value and delete it
                        value = ent['value']

                        try:
                            bam.deleteDNSDeploymentOption(confid, "forwarding-policy", server_id)
                            do_success = True
                        except ValueError as e:
                                logMsg = "Failure: %s Failed to delete DNS forwarding-policy option" % ( str(e) )
                                print_log.go(log_error, logMsg)
                                BAM.bam_logout(bam)
                                return(1)
                        else:
                            logMsg =  ('Success: delete DNS forwarding-policy option:"%s" '
                                'server:"%s" in config:"%s"') % (
                                value, server, configuration)
                            print_log.go(log_info, logMsg)
                            BAM.bam_logout(bam)
                            return(0)
                    break

                #ndof if server.upper() ==  server_name.upper(): # --- found target server to add
            # end of for ent in result_list:
            
            # if not found, will break to herer by "for ent in result_list:"
                
            if not do_success:
                logMsg = 'Failure: -s "%s" server name not found' % server
                print_log.go(log_error, logMsg)
                BAM.bam_logout(bam)
                return (1)
                
        elif do_config_serverGroup_go:
            # -----------------------------------------------------------------
            # add option to serverGroup in config
            # python dns_forwardingPolicy_add.py    -c config1 -g sg1 -o 
            # python dns_forwardingPolicy_delete.py -c config1 -g sg1
            # -----------------------------------------------------------------
            
            # --- get serversGroup in configid ---
            try:
                result_list = bam.getEntities(confid, "ServerGroup", 0, max_obj_count)
            except ValueError as e:
                logMsg = "Failure: %s Failed to get serverGroup: %s" % (str(e), server)
                print_log.go(log_error, logMsg)
                BAM.bam_logout(bam)
                return(1)
            
            do_success = False
            
            if debug_api:
                print('[debug: ------- print all serverGroup -------]')
                print(result_list)
            
            for ent in result_list:
                properties = bam.splitProp(ent)
                serverGroup_id = ent['id']
                serverGroup_name = ent['name']
                                    
                if serverGroup.upper() ==  serverGroup_name.upper(): # --- found target server to add
                    
                    try:
                        ent = bam.getDNSDeploymentOption(confid, "forwarding-policy", serverGroup_id)
                        if debug_api:
                            print('[debug: ------- search result of getDNSDeploymentOption() -------]')
                            print(ent)
                    except ValueError as e:
                            logMsg = "Failure: %s Failed to search DNS forwarding-policy option" % ( str(e) )
                            print_log.go(log_error, logMsg)
                            BAM.bam_logout(bam)
                            return(1)
                        
                    if ent['id']== 0:
                        logMsg = ('Failure: DNS forwarding-policy option of serverGroup:"%s" in config:"%s" '
                                   'does not exist') % (serverGroup, configuration)
                        print_log.go(log_error, logMsg)
                        BAM.bam_logout(bam)
                        return(1)
                    
                    else: #found option, get value and delete it
                        value = ent['value']
                    
                        try:
                            bam.deleteDNSDeploymentOption(confid, "forwarding-policy", serverGroup_id)
                            
                            do_success = True
                            
                        except ValueError as e:
                                logMsg = "Failure: %s Failed to add DNS forwarding-policy option" % ( str(e) )
                                print_log.go(log_error, logMsg)
                                BAM.bam_logout(bam)
                                return(1)
                        else:    
                            logMsg = ('Success: delete DNS forwarding-policy option:"%s" '
                            'in serverGroup:"%s" in config:"%s"') % (
                                value, serverGroup, configuration)
                            print_log.go(log_info, logMsg)
                        
                        break # for ent in result_list:

            # end of for ent in result_list:
            # if not found, will break to herer by for ent in result_list:
            
            if not do_success:
                logMsg = 'Failure: -g "%s" serverGroup name not found' % serverGroup
                print_log.go(log_error, logMsg)
                BAM.bam_logout(bam)
                return (1)
            
        elif do_server_go:
            # -----------------------------------------------------------------
            # add option [to server only by flag -y ] (config id need to be provided)
            # python dns_forwardingPolicy_add.py    -c config1 -s dds1 -y -o 
            # python dns_forwardingPolicy_delete.py -c config1 -s dds1 -y
            # -----------------------------------------------------------------
            try:
                result_list = bam.getEntities(confid, "Server", 0, max_obj_count)
            except ValueError as e:
                logMsg = "Failure: %s Failed to get server: %s" % (str(e), server)
                print_log.go(log_error, logMsg)
                BAM.bam_logout(bam)
                return(1)

            if debug_api:
                print('[debug: ------- print all servers in config -------]')
                for ent in result_list:
                    print (ent)
            do_success = False
            
            for ent in result_list:

                properties = bam.splitProp(ent)
                server_id = ent['id']
                server_name = ent['name']
                
                if server.upper() ==  server_name.upper(): # --- found target server to add
                    try:
                        ent = bam.getDNSDeploymentOption(server_id, "forwarding-policy", server_id)
                        if debug_api:
                            print('[debug: ------- search result of getDNSDeploymentOption() -------]')
                            print(ent)
                        
                    except ValueError as e:
                            logMsg = "Failure: %s Failed to search DNS forwarding-policy option" % ( str(e) )
                            print_log.go(log_error, logMsg)
                            BAM.bam_logout(bam)
                            return(1)
                        
                    if ent['id']== 0:
                        logMsg = 'Failure: DNS forwarding-policy option of server:"%s" does not exist' % (server)
                        print_log.go(log_error, logMsg)
                        BAM.bam_logout(bam)
                        return(1)
                    
                    else: #found option, get value and delete it
                        value = ent['value']
                        split_value = value.split(",")
                        ip_join = ''
                        for i in range(1,len(split_value)) :
                            if i==1:
                                ip_join = split_value[i]
                            else:
                                ip_join = ip_join + ','+ split_value[i]
                        disable_forward_child_zones = split_value[0]
                    
                        try:
                            bam.deleteDNSDeploymentOption(server_id, "forwarding-policy", server_id)
                            do_success = True
                        except ValueError as e:
                                logMsg = "Failure: %s Failed to delete DNS forwarding-policy option" % ( str(e) )
                                print_log.go(log_error, logMsg)
                                BAM.bam_logout(bam)
                                return(1)
                        else:    
                            logMsg = ('Success: delete DNS forwarding-policy option "%s" '
                                      '[Disable forwarding-policy for Child zone]:"%s" of server:"%s"') % ( 
                                      ip_join, disable_forward_child_zones, server)
                            print_log.go(log_info, logMsg)
                        
                        break
              
            # end of for ent in result_list:
            
            # if not found, will break to herer by "for ent in result_list:"
                
            if not do_success:
                logMsg = 'Failure: -s "%s" server name not found' % server
                print_log.go(log_error, logMsg)
                BAM.bam_logout(bam)
                return (1)
        
        elif do_serverGroup_go:
            # -----------------------------------------------------------------
            # add option [to serverGroup only by flag -y ] (config id need to be provided)
            # python dns_forwardingPolicy_add.py   -c config1 -g sg1 -y -o 
            # python dns_forwardingPolicy_delete.py -c config1 -g sg1 -y
            # -----------------------------------------------------------------
            # --- get serversGroup in configid ---
            try:
                result_list = bam.getEntities(confid, "ServerGroup", 0, max_obj_count)
            except ValueError as e:
                logMsg = "Failure: %s Failed to get serverGroup: %s" % (str(e), server)
                print_log.go(log_error, logMsg)
                BAM.bam_logout(bam)
                return(1)
            
            do_success = False
            
            if debug_api:
                print('[debug: ------- print all serverGroup -------]')
                print(result_list)
            
            for ent in result_list:

                properties = bam.splitProp(ent)
                serverGroup_id = ent['id']
                serverGroup_name = ent['name']
                                    
                if serverGroup.upper() ==  serverGroup_name.upper(): # --- found target server to add
                
                    try:
                        ent = bam.getDNSDeploymentOption(serverGroup_id, "forwarding-policy", serverGroup_id)
                        if debug_api:
                            print('[debug: ------- search result of getDNSDeploymentOption() -------]')
                            print(ent)
                        
                    except ValueError as e:
                            logMsg = "Failure: %s Failed to search DNS forwarding-policy option" % ( str(e) )
                            print_log.go(log_error, logMsg)
                            BAM.bam_logout(bam)
                            return(1)
                        
                    if ent['id']== 0:
                        logMsg = 'Failure: DNS forwarding-policy option of serverGroup:"%s" does not exist' % (serverGroup)
                        print_log.go(log_error, logMsg)
                        BAM.bam_logout(bam)
                        return(1)
                    
                    else: #found option, get value and delete it
                        value = ent['value']
                    
                        try:
                            bam.deleteDNSDeploymentOption(serverGroup_id, "forwarding-policy", serverGroup_id)
                            do_success = True
                        except ValueError as e:
                            logMsg = "Failure: %s Failed to add DNS forwarding-policy option" % ( str(e) )
                            print_log.go(log_error, logMsg)
                            BAM.bam_logout(bam)
                            return(1)
                        else:    
                            logMsg = ('Success: delete DNS forwarding-policy option:"%s" '
                                  'of serverGroup:"%s"') % (
                                  value, serverGroup)
                            print_log.go(log_info, logMsg)
                    
                        break # for ent in result_list:
                        
                #endof if serverGroup.upper() ==  serverGroup_name.upper(): # --- found target server to add
            # end of for ent in result_list:
            
            # if not found, will break to herer by "for ent in result_list:"
            
            if not do_success:
                logMsg = 'Failure: -g "%s" serverGroup name not found' % serverGroup
                print_log.go(log_error, logMsg)
                BAM.bam_logout(bam)
                return (1)

        #endof if configuration:

    except ValueError as e:     # except fosr any api error
        logMsg = "%s" % ( str(e) )
        print_log.go(log_error, logMsg)
        BAM.bam_logout(bam) 
        return(1)
# ---------------------------------------------------------------------
# start
# ---------------------------------------------------------------------
if __name__ == '__main__':
    dns_forwardingPolicy_delete()    
