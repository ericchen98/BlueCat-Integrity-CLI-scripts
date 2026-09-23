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
# v1.0-20260919 created (same style as dnsRole_delete.py/dnsRole_query.py)
#
# some usage:
#
# ------ change dds1 (existing role [MASTEr]/[network_int] to new role [SECONDARY]/publish_int [a1.xyz.corp]
# python3 dnsRole_update.py -c config1 -v view1 -z red.corp -s dds1 --nr slave --np a1.xyz.corp
# INFO:Success: updated DNS Deployment role for server dds1: PRIMARY -> SECONDARY -> interface: 
# PublishedInterface:a1.xyz.corp(10.1.1.11)
#
# ------ change dds1 (existing role [SLAVE]/pub_int[a1.xyz.corp] to new role:[PRIMARY]/pub_int [a1.xyz.corp]
# python3 dnsRole_update.py -c config1 -v view1 -z red.corp -s dds1 -p a1.xyz.corp  --nr master
# INFO:Success: updated DNS Deployment role for server dds1: SECONDARY -> PRIMARY -> interface: 
# PublishedInterface:a1.xyz.corp(10.1.1.11)
#


'''
dnsRole_update -c config1 -v view1 -z test.corp -s dds1 --nr secondary
# change the DNS deployment role of server "dds1" on zone "test.corp" under view "view1" to "secondary"

    -c   config_name
    -v   view_name
    -z   zone_name
    -s   dds_name                       # server whose role is being changed
    --nr new_role                       # new role [primary|secondary|primary_hidden|hidden_primary|
                                        #           recursion|forwarder|stub|slave_stealth|hidden_slave|none]
    -p   publish_interface_hostname     # optional: existing role is looked up via this
                                        #           published interface instead of the server's network interface
    --np new_publish_interface_hostname # optional: also move the role to this new published interface
    
    Note: if publish interface exists, you must provide -p to modify server role. E.g. the following command change
          the DNS role of dds1 (publish interface pub1.xyz.corp) to role primary with publish interface pub1.xyz.corp
          
          dnsRole_update.py -c config1 -v view1 -z red.corp -s dds1 -p pub1.xyz.corp  --nr master
    
'''

import getopt
import sys
import json
import os

import BAM

# ------------- module from internet ---------
import urllib3  # to suppress https cert worning
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


version = "1.0"

# to disable exception trackback information (if not set, urllib3 excpetion will be printed to screen)
sys.tracebacklimit = 0


# ---------------------------------------------------------------------
# main function
# ---------------------------------------------------------------------
def dnsRole_update(*args):

    # -------------------------------------------------------------------------------
    # define log_prog_type_index : to be called in BAM.print_log()
    # -------------------------------------------------------------------------------
    prog_type_view = 0
    prog_type_add = 1
    prog_type_delete = 2
    prog_type_update = 3
    prog_type_other = 4

    # set log_prog_type_index by script type (view, add, delete etc.) will print eg "view" in log
    log_prog_type_index = prog_type_update

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
    record_changed = False

    # log_info_error = 0(info), 1(error). This is used to call bam.print_log()
    log_info = 0
    log_error = 1

    # read max obj count in API
    max_obj_count = "1000"

    # ------------------------------------------
    configuration = None

    view = None
    zone = None

    confid = 0
    viewid = 0
    zoneid = 0

    show_version = False

    targetId = 0

    newroletype = None
    servername = None

    publishHostname = ''
    newPublishHostname = ''

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
            opts, args = getopt.getopt(  input_args, "ndc:v:z:s:p:h", ["nr=","np=","debug=","version"])
        else: # call this script from CLI. Parsing "sys.argv[1:]" ([1:] - not include script name)
            opts, args = getopt.getopt(sys.argv[1:], "ndc:v:z:s:p:h", ["nr=","np=","debug=","version"])
    except getopt.GetoptError as e:
        logMsg = str(e)
        print_log.go(log_error, logMsg)
        return(1)

    for o,v in opts:
        if o == "-d": debug = True
        elif o == "-c": configuration = v
        elif o == "-v": view = v
        elif o == "-z": zone = v
        elif o == "-s": servername = v
        elif o == "--nr": newroletype = v
        elif o == "-p": publishHostname = v
        elif o == "--np": newPublishHostname = v
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

    if (not servername) or (servername[0:1] == "-"):
        logMsg = "Failure: -s servername option is required"
        print_log.go(log_error, logMsg)
        return(1)

    if (not newroletype) or (newroletype[0:1] == "-"):
        logMsg = "Failure: --nr new_role option is required"
        print_log.go(log_error, logMsg)
        return(1)

    #translate newroletype to upper case (need to be 'PRIMARY'/'SECONDARY'/etc)
    newroletype = newroletype.upper()

    # same v1-word -> real v2 roleType enum translation as dnsRole_add.py/
    # dnsRole_delete.py (CONFIRMED live acceptedValues: PRIMARY,
    # MULTI_PRIMARY, HIDDEN_PRIMARY, HIDDEN_MULTI_PRIMARY, SECONDARY,
    # STEALTH_SECONDARY, FORWARDING, STUB, RECURSIVE, NONE).
    if newroletype == 'MASTER':
        newroletype = 'PRIMARY'
    if newroletype == 'SLAVE':
        newroletype = 'SECONDARY'
    if newroletype in ('MASTER_HIDDEN', 'HIDDEN_MASTER', 'PRIMARY_HIDDEN'):
        newroletype = 'HIDDEN_PRIMARY'
    if newroletype in ('SLAVE_STEALTH', 'STEALTH_SLAVE', 'SECONDARY_STEALTH',
                        'HIDDEN_SLAVE', 'HIDDEN_SECONDARY'):
        newroletype = 'STEALTH_SECONDARY'
    if newroletype in ('RECURSION',):
        newroletype = 'RECURSIVE'
    if newroletype in ('FORWARDER',):
        newroletype = 'FORWARDING'

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
    targetId = 0     # "targetId" is the object id the role is on
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
                    # targetId is the id the role is looked up on
                    # note: if zone is given, this view's targetId will be overwritten by zone's id
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
                        targetId = zoneid
                    # ------------------------------------------------
                    # End of read config/view/zone
                    # ------------------------------------------------

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

                properties = bam.splitProp(ent)
                fullhostname = properties['fullHostName']

                if publishHostname != '':
                    ent_sif = bam.getEntityByName(serverid, publishHostname, "PublishedServerInterface")
                else: # Get Network server interface
                    ent_sif = bam.getEntityByName(serverid, fullhostname, "NetworkServerInterface")

                if debug_api:
                    print( '\n---[debug]: bam.getEntityByName( serverid, hostname,"publish | Network Interface")')
                    print(ent_sif)

                sifid = ent_sif['id']

                if sifid == 0:
                    logMsg = "Failure: Failed to get server interface %s" % view
                    print_log.go(log_error, logMsg)
                    BAM.bam_logout(bam)
                    return(1)

                # get existing dns deploy role
                try:
                    rtn_role = bam.getDNSDeploymentRole(targetId, sifid)
                except ValueError as e:
                    logMsg = "Failure: %s Failed to get DNS Deployment role %s" % (str(e), servername)
                    print_log.go(log_error, logMsg)
                    BAM.bam_logout(bam)
                    return(1)

                if debug_api:
                    print( '\n---[debug]: bam.getDNSDeploymentRole(entityId,serverInterfaceId) : %s %s' % (targetId, sifid))
                    print(rtn_role)

                roleId = rtn_role['id']

                # cannot find existing role for this server
                if roleId == 0:
                    logMsg = "Failure: No existing DNS Deployment role found for server %s" % servername
                    print_log.go(log_error, logMsg)
                    BAM.bam_logout(bam)
                    return(1)
                else: # found role - update its roleType
                    old_roletype = rtn_role['type']

                    # if --np is given, resolve the new publish interface
                    # up front - if it can't be found, stop here (same as
                    # -p above) and don't change the role at all.
                    final_sifid = sifid
                    if newPublishHostname != '':
                        ent_new_sif = bam.getEntityByName(serverid, newPublishHostname, "PublishedServerInterface")

                        if debug_api:
                            print( '\n---[debug]: bam.getEntityByName(serverid, newPublishHostname, "PublishedServerInterface")')
                            print(ent_new_sif)

                        new_sifid = ent_new_sif['id']

                        if new_sifid == 0:
                            logMsg = "Failure: Failed to get new publish interface %s" % newPublishHostname
                            print_log.go(log_error, logMsg)
                            BAM.bam_logout(bam)
                            return(1)

                        final_sifid = new_sifid

                    properties = bam.splitProp(rtn_role)
                    properties['roleType'] = newroletype
                    rtn_role['properties'] = bam.joinProp(properties)

                    if debug_api:
                        print ('------ Ent to be used by bam.update(ent) -------')
                        print (rtn_role)

                    try:
                        bam.update(rtn_role)
                        record_changed = True

                    except ValueError as e:
                        logMsg = "Failure: %s Failed to update DNS Deployment role %s" % (str(e), servername)
                        print_log.go(log_error, logMsg)
                        error_Logged = True

                    # --np: also move the role to the new published interface
                    if record_changed and newPublishHostname != '':
                        try:
                            bam.setDNSDeploymentRoleInterface(roleId, final_sifid, "PublishedInterface")

                        except ValueError as e:
                            logMsg = "Failure: %s Failed to move DNS Deployment role for server %s to publish interface %s" % (
                                    str(e), servername, newPublishHostname)
                            print_log.go(log_error, logMsg)
                            record_changed = False
                            error_Logged = True

                    if record_changed:
                        interfaceInfo = bam.describeInterface(final_sifid)
                        logMsg = "Success: updated DNS Deployment role for server %s: %s -> %s -> interface: %s" % (
                                servername, old_roletype, newroletype, interfaceInfo)
                        print_log.go(log_info, logMsg)

                        BAM.bam_logout(bam)
                        return(0)
                    else:
                        if not error_Logged:
                            logMsg = "Failure: failed to update DNS Deployment role for server %s" % servername
                            print_log.go(log_error, logMsg)
                        BAM.bam_logout(bam)
                        return(1)

    except ValueError as e:     # except fosr any api error
        logMsg = "%s" % ( str(e) )
        print_log.go(log_error, logMsg)
        BAM.bam_logout(bam)
        return(1)

# ---------------------------------------------------------------------
# main()
# ---------------------------------------------------------------------
if __name__ == '__main__':
    dnsRole_update()
