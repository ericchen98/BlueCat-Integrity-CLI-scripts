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
# v1.2-20230828 fixed log does not show in cli.py issue 
# v1.1-20230827 rename host-append.py to host-add-one.py
# v1.0-20220317 created
#
# debug switch
#   -d         # print additonal user info
#   --debug=1  # print script debug print
#   --debug=2  # print bam.py debug info e.g. API http request

'''
host-add-one -c config1 -v view1 -z test.corp -r host1 -i 10.1.1.3 

    -c  config_name
    -v  view_name
    -z  zone_name
    -r  record_name
    -i  rdata

    # host_add:     Add a host record with one or multiple IP to a zone
    # host_add_one: append an IP to existing IP list of host record
'''
import getopt
import sys
import json
import ipaddress
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

version = "1.2"

# to disable exception trackback information (if not set, urllib3 excpetion will be printed to screen)
sys.tracebacklimit = 0

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
# convertRR = True | False //whether to convert RR to lower cases when add/delete/query
#   A record: convert RR_Name
#-------------------------------------------
convertRR = False

# ---------------------------------------------------------------------
# main function
# ---------------------------------------------------------------------
def host_add_one(*args):    

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
    log_prog_type_index = prog_type_update

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
    
    api=''
    apiPw=''
    https=False

    configuration = None
    view = None
    zone = None
    rrName = None
    rdata = None
    newrdata = None
    matchclient = None
    user = None
    show_version = False
    
    addptr_yn = ''
    addptr= False
    addptr_yn_set = False
    
    confid = 0
    viewid = 0
    zoneid = 0

    ViewToGet = None
    ZoneToGet = None
    HostsToGet = None

    sameAsZone = None
    sameAsZone_Message = " "

    addrList = []
    ip_match = False
    index = 0
    
    propertiesString = ''

    debug_level=0
    debug1=False
    debug2=False

    foo1=None
    addrList_sort =''
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
    print_log = BAM.print_log( log_prog_type_index ,input_cmd_log, logPath, logFileName)

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
            opts, args = getopt.getopt(  input_args, "dc:v:z:r:i:p:kh",["ni=","debug=","version"])
        else: # call this script from CLI. Parsing "sys.argv[1:]" ([1:] - not include script name)
            opts, args = getopt.getopt(sys.argv[1:], "dc:v:z:r:i:p:kh",["ni=","debug=","version"])
    except getopt.GetoptError as e: 
        logMsg = str(e)
        print_log.go(log_error, logMsg)
        return(1) 

    for o,v in opts:
        if o == "-d": debug = True 
        elif o == "-c": configuration = v
        elif o == "-v": view = v
        elif o == "-z": zone = v
        elif o == "-r": rrName = v
        elif o == "-i": rdata = v
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
    # test cli parameters 
    # ---------------------------------------------------------
    if (not configuration) or (configuration[0:1] == "-"):
        logMsg = "Failure: -c config option is required"
        print_log.go(log_error, logMsg)
        return(1)

    if (not view) or (view[0:1] == "-"):
        logMsg = "Failure: -v view option is required"
        print_log.go(log_error, logMsg)
        return(1)

    if (not zone) or (zone[0:1] == "-"):
        logMsg = "Failure: -z zone option is required"
        print_log.go(log_error, logMsg)
        return(1)

    if not rdata: 
        if (rdata == None) or (rdata[0:1] == "-"):
            logMsg = "Failure: -i data option is required"
            print_log.go(log_error, logMsg)
            return(1)
            
    else: #rdata exists
        
        try:
            # this is to test whether the rdata is a valid IPv6 (and ipv4) address
            # note: to support ipv6, this script does not support adding multiple address 
            # at the same time anymore (e.g. -i 10.1.1.1,10.2.2.2). To do it, use host-add-all.py
            
            # will do exception if IP address format is wrong
            foo1 = ipaddress.ip_address(rdata)
            
        except ValueError as e:
            logMsg = "Failure: "+ str(e)
            print_log.go(log_error, logMsg)
            return(1)

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
                if zone:
                    zone_ent = bam.find_zone(viewid, zone)
                    zoneid = zone_ent['id']
                    if zoneid == 0:
                        logMsg = "Failure: Failed to get zone: %s" % (zone)
                        print_log.go(log_error, logMsg)
                        BAM.bam_logout(bam)
                        return(1)
                    # ------------------------------------------------ 
                    # End of read config/view/zone 
                    # ------------------------------------------------ 
                    
                    # ------------------------------------------------ 
                    # convert zone & rrName to lower cases to meet requirement
                    # ------------------------------------------------ 
                    if convertRR:
                        if not (zone == None):
                            zone = zone.lower()
                        if not (rrName == None):
                            rrName = rrName.lower()
                    
                    if sameAsZone:
                        absolutename = zone
                        # this is to meet API same as zone record requirement e.g. need ".test.corp"
                    else:
                        absolutename = rrName + "." + zone
                    try:
                        if sameAsZone:
                            # use rrname="" to search "same as zone" record (ignore any -r input by user)
                            ent = bam.getEntityByName( zoneid, "" , "HostRecord" )
                        else:
                            ent = bam.getEntityByName( zoneid, rrName , "HostRecord" )
                    except ValueError as e:
                        logMsg = "Failure: "+str(e) + "Error while getting Host Record"
                        print_log.go(log_error, logMsg)
                        BAM.bam_logout(bam)
                        return(1)

                    if debug_api:
                        print ('\n[debug: ------- search result of getEntityByName() -------]')
                        print (ent)
                        print ()

                    if ent['id'] == 0:  # no existing record found. Do nothing, exist
                        logMsg = "Failure: record %s not found" % (absolutename)
                        print_log.go(log_error, logMsg)
                        BAM.bam_logout(bam)
                        return(1)
                    else:   # of if ent['id'] == 0: 
                        # Found host record, try to add ip to address list. 
                        properties = bam.splitProp(ent)
                        
                        # print (properties)  # output:
                        # {'absoluteName': 'h1.test.corp', 'addresses': '10.1.1.10,10.1.1.11', 
                        #    'addressIds': '171544,171546', 'reverseRecord': 'true'}
                      
                        addrList = properties['addresses'].split(',')
                        
                        # print addrList, len(addrList)
                        # ['10.10.10.4', '10.10.10.38', '2001:DB8:0:0:0:0:0:10', '2001:DB8:0:0:0:0:0:11']
                        # 4 <----- len(addrList)
                        
                        # how many IP in address list = len(addrList)
                        total_ip_count=len(addrList)
                        
                        ip_match = False
                        index = 0 
                        
                        for index in range(len(addrList)):
                            if ipaddress.ip_address(addrList[index]) == ipaddress.ip_address(rdata):
                                # use ipaddress.ip_address module to compare existing ipv4&ipv6 ip and rdata
                                #   this is the easier way that don't need to handle upper/lower cases
                                #   & IPv6 format. It also support ipv4 & ipv4 at same time
                                
                                ip_match = True
                                break
                                
                            #endof if ipaddress.ip_address(addrList[index]) == ipaddress.ip_address(rdata):
                        # endof for index in range(len(addrList)):

                        if ip_match == False:
                            # no match,  add IP
                                #xxxxxxxxxxxxxxxxxx
                            old_IPList = properties['addresses'] 
                            properties['addresses']  = properties['addresses'] + ',' + rdata
                            
                            ent['properties'] = bam.joinProp(properties)
                            

                            if debug_api: 
                                print('[debug: ------- new data to be updated -------]')
                                print( ent )
                            
                            try:
                                bam.update (ent)
                                logMsg =  "Success: append %srecord %s IP %s to %s " % ( 
                                            sameAsZone_Message, absolutename, rdata, str(old_IPList) )
                                print_log.go(log_info, logMsg)
                                record_changed = True
                            except ValueError as e:
                                #raise ValueError, "Failed to update record: %s" % absolutename
                                logMsg = "Failure: %s Failed to update%srecord: %s" % ( str(e), 
                                            sameAsZone_Message, absolutename)
                                print_log.go(log_error, logMsg)
                                BAM.bam_logout(bam)
                                return(1)
                        else: # if ip_match == False:
                            logMsg = "Failure:%shost record %s has this IP %s already" % ( sameAsZone_Message, 
                                        absolutename, rdata)
                            print_log.go(log_error, logMsg)
                        
                        #if debug_level >= debug_user:
                        #    print ("\nDebug:%srecord %s: %s" % ( sameAsZone_Message, 
                        #            absolutename, properties['addresses']) )
                        
                        print ("Current%sHost record %s: %s " % ( sameAsZone_Message, 
                                absolutename, properties['addresses']) )
                                
                        #endof if ip_match == False:
                    #end if ent['id'] == 0:
                #end if zone:
            #end if view:
        #end if configuration:
        BAM.bam_logout(bam)
        return(0)
        
    except ValueError as e:     # except fosr any api error
        logMsg = "%s" % ( str(e) )
        print_log.go(log_error, logMsg)
        BAM.bam_logout(bam) 
        return(1)
# ---------------------------------------------------------------------
# start
# ---------------------------------------------------------------------
if __name__ == '__main__':
    host_add_one()
    
