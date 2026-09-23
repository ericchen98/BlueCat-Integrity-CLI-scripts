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
# BAM ver: 26.1
#
# v5.7-20251228 modify debug output format
# v5.6-20230828 fixed log does not show in cli.py issue 
# v5.5-20230612 support publish interface
# v5.4-20221226 change log dir to "./"
# v5.3-20220221 update BAM.bam_logout(bam) before all return()
# v5.1 20210921
# v5.0 20210915-1500
# v4.0 2021/7/8 use new BAM.py (created by Eric Chen) 
#       - modify to work with python 3
#       - use bam.find_zone() instead of split fqdn loop search
#       - use print_log class in BAM.py
# note; 
#       - can add different roles,  e.g. recursion, forwarder etc. not only master&slave
#       - for 9.3, server type cannot be "primary" or "secondary". It needs to be "master"/"slave"

'''
dnsRole-delete -c config1 -v view1 -r master -s dds1
# delete server "dds1" as DNS master role from view "view1" 

dnsRole-delete -c config1 -v view1 -z test.corp -r master -s dds1
# delete server "dds1" as DNS master role from zone "test.corp" under view "view1" 

    -c config_name
    -v view_name
    -z zone_name
    -r role [master|slave|master_hidden|recursion|forwarder|stub|slave_stealth|none]
    -s dds_name

    # deletes the role matching both -r and -s 
'''

import getopt
import sys
import json
import os

import BAM

# ------------- module from internet ---------
import urllib3  # to suppress https cert worning
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


version = "5.8"

# to disable exception trackback information (if not set, urllib3 excpetion will be printed to screen)
sys.tracebacklimit = 0


# ---------------------------------------------------------------------
# main function
# ---------------------------------------------------------------------
def dnsRole_delete(*args):    

    # -------------------------------------------------------------------------------
    # define log_prog_type_index : to be called in BAM.print_log()
    # -------------------------------------------------------------------------------
    prog_type_view = 0
    prog_type_add = 1
    prog_type_delete = 2
    prog_type_update = 3
    prog_type_other = 4

    # set log_prog_type_index by script type (view, add, delete etc.) will print eg "view" in log
    log_prog_type_index = prog_type_delete

    # ---------------------------------------------------------------------
    # var setup
    # ---------------------------------------------------------------------
    # default = 3 sec. If change any  other number, it will overwrite REST requests timeout value
    req_timeout = 5

    logMsg = ''
    cmdLine = ''
    input_cmd = ''
    input_cmd_log = ''

    error_Logged = False    # True when bam.update exception is called

    # log_info_error = 0(info), 1(error). This is used to call bam.print_log()
    log_info = 0
    log_error = 1


    # read max obj count in API
    max_obj_count = "1000"

    # ------------------------------------------
    configuration = None

    view = None
    zone = None
    rrName = None
    rdata = None
    matchclient = None
    user = None

    confid = 0
    viewid = 0
    zoneid = 0
    
    show_version = False

    targetId = 0

    roletype = None
    servername = None


    ViewToGet = None
    ZoneToGet = None
    HostsToGet = None

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
    
    
    # --------------------------------------------------------------
    # load config by BAM.load_config()  return json format "config"
    # --------------------------------------------------------------
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
            opts, args = getopt.getopt(  input_args, "ndc:v:z:r:s:h", ["debug=","version"])
        else: # call this script from CLI. Parsing "sys.argv[1:]" ([1:] - not include script name)
            opts, args = getopt.getopt(sys.argv[1:], "ndc:v:z:r:s:h", ["debug=","version"])
    except getopt.GetoptError as e: 
        logMsg = str(e)
        print_log.go(log_error, logMsg)
        return(1) 
        
    for o,v in opts:
        if o == "-d": debug = True 
        elif o == "-c": configuration = v
        elif o == "-v": view = v
        elif o == "-z": zone = v
        elif o == "-r": roletype = v
        elif o == "-s": servername = v
        elif o == "--version": show_version = True
        elif o == "--debug": debug_input = v  
        elif o == "-h":
            print (__doc__)
            return(0)

    if not opts:
        print (__doc__)
        return(0)


    if show_version == True:
        print("Version %s" % version)
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

    # ---------------------------------------------------------
    # test cli required parameters 
    # ---------------------------------------------------------
    if (not configuration) or (configuration[0:1] == "-"):
        logMsg = "Failure: -c config option is required"
        print_log.go(log_error, logMsg)
        return(1)

    if (not view) or (view[0:1] == "-"):
        logMsg = "Failure: -v view option is required"
        print_log.go(log_error, logMsg)
        return(1)
        
    if (not roletype) or (roletype[0:1] == "-"):
        logMsg = "Failure: -r roletype option is required"
        print_log.go(log_error, logMsg)
        return(1)        

    if (not servername) or (servername[0:1] == "-"):
        logMsg = "Failure: -s servername option is required"
        print_log.go(log_error, logMsg)
        return(1)

    #translate roletype to upper case (need to be 'MASTER' or 'SLAVE'
    roletype=roletype.upper()

    # CONFIRMED live (dnsRole_delete.py -r master: "existing DNS Deployment
    # role: DNSDeploymentRole does not match input role: MASTER") - the
    # server's real roleType enum uses PRIMARY/SECONDARY/etc, not v1's
    # MASTER/SLAVE words, so this needs the same translation dnsRole_add.py
    # applies before comparing/sending it.
    if roletype == 'MASTER':
        roletype = 'PRIMARY'
    if roletype == 'SLAVE':
        roletype = 'SECONDARY'
    if roletype in ('MASTER_HIDDEN', 'HIDDEN_MASTER', 'PRIMARY_HIDDEN'):
        roletype = 'HIDDEN_PRIMARY'
    if roletype in ('SLAVE_STEALTH', 'STEALTH_SLAVE', 'SECONDARY_STEALTH',
                    'HIDDEN_SLAVE', 'HIDDEN_SECONDARY'):
        roletype = 'STEALTH_SECONDARY'
    if roletype in ('RECURSION',):
        roletype = 'RECURSIVE'
    if roletype in ('FORWARDER',):
        roletype = 'FORWARDING'

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
    # get config/view/zone
    # ----------------------------------------------------------------
    err_msg = ''   
    targetId = 0     # "targetId" is the object id to add/delete role
    try:
        if configuration:
            config_ent = bam.getEntityByName("0", configuration, "Configuration")
            confid = config_ent['id']
            if confid == 0:
                logMsg = "Failure: Failed to get configuration: %s" % (configuration)
                print_log.go(log_error, logMsg)
                BAM.bam_logout(bam)
                return(1)

            if view:
                view_ent = bam.getEntityByName(confid, view, "View")
                viewid = view_ent['id']
                if viewid == 0:
                    logMsg = "Failure: Failed to get view: %s" % (view)
                    print_log.go(log_error, logMsg)
                    BAM.bam_logout(bam)
                    return(1)
                else:
                    # targetId is the id to add/del DNSDeployRole
                    # note: if zone is given, this view's addtargetId will be overwrite by zone's id
                    # the dns role will be add to zone 
                    targetId = viewid

                if zone:
                    zone_ent = bam.find_zone(viewid, zone)
                    zoneid = zone_ent['id']
                    if zoneid == 0:
                        logMsg = "Failure: Failed to get zone: %s" % (zone)
                        print_log.go(log_error, logMsg)
                        BAM.bam_logout(bam)
                        return(1)
                    else:
                        # targetId is the id to add/del DNSDeployRole
                        targetId = zoneid
                        
                    # ------------------------------------------------ 
                    # End of read config/view/zone 
                    # ------------------------------------------------ 

                    # if zone is None, targetId will be still view's id. 
                    #   The role will be assigned to view

                if debug_api: 
                    print( '\n---[debug]: find_zone() result - configId=%s ViewId=%s ZoneId=%s' % (confid, viewid, zoneid) )

                # Get Server hostname
                ent = bam.getEntityByName(confid, servername, "Server")
                serverid = ent['id']
                
                if debug_api: 
                    print( '\n---[debug]: bam.getEntityByName(confid=%s, servername=%s, "Server")' % (confid, servername) )
                    print(ent)

                if serverid == 0:
                    logMsg = "Failure: Failed to get server: %s" % servername
                    print_log.go(log_error, logMsg)
                    BAM.bam_logout(bam)
                    return(1)

                # match purely by role + server name - the role can be
                # attached via any of the server's interfaces (plain
                # network or published), so there's no need to resolve a
                # specific interface at all here.
                try:
                    rtn_role = bam.getDNSDeploymentRoleByServer(targetId, serverid)

                except ValueError as e:
                    logMsg = "Failure: %s Failed to get DNS Deployment role %s" % (str(e),servername)
                    print_log.go(log_error, logMsg)
                    BAM.bam_logout(bam)
                    return(1)

                if debug_api:
                    print( '\n---[debug]: bam.getDNSDeploymentRoleByServer(entityId,serverId) : %s %s' % (targetId, serverid))
                    print(rtn_role)
                
                #print(rtn_role)
                #{'id': 171975, 'type': 'MASTER', 'service': 'DNS', 'entityId': 171826, 
                #  'serverInterfaceId': 100896, 'properties': 'readOnly=false|nsRecordTTL=86400|inherited=false|'}
                
                roleId = rtn_role['id']
                
                # cannot find getDNSDeploymentRole of servername
                if roleId == 0:
                    logMsg = "Failure: Failed to get DNS deploy Role %s" % servername
                    print_log.go(log_error, logMsg)
                    BAM.bam_logout(bam)
                    return(1)
                else: #end_id != 0, found DNSDeploymentRole 
                    if not (rtn_role['type']) == roletype:   # not match, print error msg
                        logMsg = "Failure: Server %s existing DNS Deployment role: %s does not match input role: %s" % (
                            servername, rtn_role['type'], roletype )
                        print_log.go(log_error, logMsg)
                        BAM.bam_logout(bam)
                        return(1)
                        
                    else: # type match. Delete it
                        try:
                            rtn = bam.delete(roleId)
                            # success delete
                            if zone == None:
                                logMsg = "Success: delete %s of %s on view:%s" % (servername, roletype, view)
                            else:
                                logMsg = "Success: delete %s of %s on view/zone:%s/%s" % (servername, roletype, view, zone)
                            print_log.go(log_info, logMsg)
                            
                        except ValueError as e:
                            logMsg = "Failure: %s Failed to delete DNS Deployment role %s" % (str(e),servername)
                            print_log.go(log_error, logMsg)
                            BAM.bam_logout(bam)
                            return(1)
                    #endof if not (ent['type']) == roletype:   # not match, print error msg
                    BAM.bam_logout(bam)
                    return(0)
                    
    except ValueError as e:     # except fosr any api error
        logMsg = "%s" % ( str(e) )
        print_log.go(log_error, logMsg)
        BAM.bam_logout(bam) 
        return(1)

# ---------------------------------------------------------------------
# main()
# ---------------------------------------------------------------------
if __name__ == '__main__':
    dnsRole_delete()
    
