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
# v5.8-20230828 fixed log does not show in cli.py issue 
# v5.7-20230827 update help
# v5.6-20221220
#       1) modified: logPath = "./"
#       2) add flag convertRR=True to convert RR Name and rdata to "lower case".
# v5.5-20220402 rename host-delete.py to host-delete-one.py to meet backward compatibility 
# v5.4-20220221 update BAM.bam_logout(bam) before all return()
# v5.3 20210110 update help
# v5.1-20210921 (use BAM.py v20210918-1735)
# v5.0 20210915-1500
# v3.0 use new BAM that work with 9.3 & REST
# v2.3 2020/5/26 read config file from dir: /opt/bluecat/cli
# v2.2 2020/5/6 add log function (csv)
# v2.1 change handle IP logic: add IP to properties['addresses']
# v2.0 2020-0318 add "same as zome" -k record support
#                   it is possible that we have multiple same as zome recrod, 
#                   but we can only ONE same as zone "Host record"
#

'''
host-delete-one -c config1 -v view1 -z test.corp -r host1 -i 10.10.10.3
host-delete-one -c config1 -v view1 -z test.corp -i 10.10.10.3 -k  (update "same as zome" record)

    -c config name
    -v view name
    -z zone name
    -r record name
    -i rdata
    -k same as zome record (when -k is used, -r is ignored)

    # delete an IP from a host record
'''
import getopt
import sys
import json
import os
import ipaddress

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

version = "5.8"

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
# convertRR = False | False //whether to convert RR to lower cases when add/delete/query
#   A record: convert RR_Name
#-------------------------------------------
convertRR = False

# ---------------------------------------------------------------------
# main function
# ---------------------------------------------------------------------
def host_delete_one(*args):    

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
    log_prog_type_index = prog_type_delete

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

    noisy = True
    doit = True
    
    # ------------------------------------------ for debug
    debug = False           # -d of getopt() 
    debug_input = None      # input (type str) of getopt()
    debug_user = False
    debug_api  = False
    debug_bam  = False
    # ------------------------------------------ others
    configuration = None
    view = None
    zone = None
    rrName = None
    rdata = None
    matchclient = None
    user = None
    show_version = False

    confid = 0
    viewid = 0
    zoneid = 0

    ViewToGet = None
    ZoneToGet = None
    HostsToGet = None

    sameAsZone = None
    sameAsZone_Message = ""

    addrList = []
    ip_match = False
    index = 0
    addptr= False
    propertiesString = ''


    foo1=None
    i = 0
    total_ip_count=0
    addrList_new = ''

    DoIt=False
    cmdLine = ""

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
            opts, args = getopt.getopt(  input_args, "dc:v:z:r:i:kph", ["debug=","version"])
        else: # call this script from CLI. Parsing "sys.argv[1:]" ([1:] - not include script name)
            opts, args = getopt.getopt(sys.argv[1:], "dc:v:z:r:i:kph", ["debug=","version"])
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
        elif o == "-p": addptr= True
        elif o == "-k": sameAsZone = True
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

    if not sameAsZone:  # -k is not set
        if (rrName == None) or (rrName[0:1] == "-"):
            logMsg = "Failure: -r rrName option is required"
            print_log.go(log_error, logMsg)
            return(1)

    if sameAsZone:
        sameAsZone_Message = " SAME AS ZONE "
    else:
        sameAsZone_Message = " "

    
    if not rdata:  # -k is not set
        if (rdata == None) or (rdata[0:1] == "-"):
            logMsg = "Failure: -i data option is required"
            print_log.go(log_error, logMsg)
            return(1)
    else:
        #rdata exists
        
        # conver it to upper case for IPv6 address (no change to ipv4 addr) - no need if use ipaddress module
        #rdata = rdata.upper()

        # convert 2001:db8::56 to 2001:db8:0:0:0:0:0:56 (No need here)
        # foo1 = ipaddress.ip_address(unicode(rdata)).exploded
        # foo2 =':'.join('0' if i=='0000' else i.lstrip('0') for i in foo1.split(':'))
        #print "=========ipv6>", foo2 
        # output 2001:db8:0:0:0:0:0:56

        try:
            # this is to test whether the rdata is a valid IPv6 (and ipv4) address
            # note. this program does not support adding multiple address 
            #    at the same time anymore (e.g. -i 10.1.1.1,10.2.2.2)
            # to support it, need to add handle -i rdata as array. To be done in future.
            
            foo1 = ipaddress.ip_address(rdata)
            
        except ValueError as e:
            logMsg = "Failure: "+ str(e)
            print_log.go(log_error, logMsg)
            return(1)

    if addptr:
        reverse= "reverseRecord=True"
    else:
        reverse= "reverseRecord=False"
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
                        absolutename =  zone
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
                        print()


                    if ent['id'] == 0:  # host record NOT found. Do nothing, exist
                        logMsg = "Failure: record %s not found" % (absolutename)
                        print_log.go(log_error, logMsg)
                        BAM.bam_logout(bam)
                        return(1)
                    else:
                        # Found host record and update it. 
                        # Use ent_json['properties'] / properties['addresses'] to setup properties

                        properties = bam.splitProp(ent)
                        
                        # print (properties)
                        # output:
                        # {'absoluteName': 'h3.test.corp', 'addresses': '10.1.1.1,10.1.1.2', 
                        # 'addressIds': '171543,171553', 'reverseRecord': 'false'}

                        addrList = properties['addresses'].split(',')
                        
                        # sort() might be used!!
                        # addrList.sort()
                        # print addrList
                        #
                        # addrList = 
                        # ['10.10.10.4', '10.10.10.38', '2001:DB8:0:0:0:0:0:10', '2001:DB8:0:0:0:0:0:11']
                        # len(addrList)=4                    
                        # how many IP in address list = len(addrList)

                        total_ip_count = len(addrList)
                        
                        ip_match = False
                        
                        # search rdata in addrList. if ip_match = True (yes, rdada is in addrList)
                        for index in range(len(addrList)):
                            if ipaddress.ip_address(addrList[index]) == ipaddress.ip_address(rdata):
                                ip_match = True
                                break
                            else:
                                ip_match = False
                        
                        # addrList[ip_position] is the IP address, will use "ip_position" to delete it latter
                        ip_position = index        

                        if ip_match == True:   # ip found, delete it from address list
                            if total_ip_count == 1:   # delete host record because there's only 1 ip
                                if sameAsZone:
                                    display_name = absolutename
                                else:
                                    display_name = rrName
                                try:
                                    bam.delete( ent['id'] )   
                                    logMsg = "Success: delete%srecord %s IP %s (record deleted)" %  (sameAsZone_Message, 
                                                display_name, rdata)
                                    print_log.go(log_info, logMsg)
                                except ValueError as e:
                                    #raise ValueError, "Failed to delete record: %s" % rrName
                                    logMsg = "Failure: %sFailed to delete%srecord: %s" % (str(e), sameAsZone_Message, rrName)
                                    print_log.go(log_error, logMsg)
                                    BAM.bam_logout(bam)
                                    return(1)

                            else: # of total_ip_count == 1:  # total_ip_count is more than 1
                                #delete target ip from addrList
                                del addrList[ip_position]
                                
                                # addrList_new is a string (to be added as properties)
                                addrList_new = ''
                                
                                for i in range (len(addrList)):
                                    if i==0:
                                        addrList_new = addrList[i]
                                    else:
                                        addrList_new =  addrList_new + ',' + addrList[i]
                                
                                properties['addresses'] = addrList_new
                                ent['properties'] = bam.joinProp(properties)
                                
                                if debug_api:
                                    print ('\n[debug: ------- entity built (to be sent by API) -------]')
                                    print (ent)
                                    print()
                                try:
                                    bam.update (ent)
                                    logMsg = "Success: delete%srecord %s IP %s (record update)" % (sameAsZone_Message, 
                                            absolutename, rdata)                                
                                    print_log.go(log_info, logMsg)
                                    record_changed = True
                                except ValueError as e:
                                    #raise ValueError, "Failed to update record: %s" % absolutename
                                    logMsg = "Failure: %s Failed to update record: %s" % ( str(e), absolutename)
                                    print_log.go(log_error, logMsg)
                                    BAM.bam_logout(bam)
                                    return(1)
                                '''
                                if debug:
                                    if total_ip_count != 1:
                                        logMsg =  "\nDebug:%srecord %s: %s" % (sameAsZone_Message,absolutename, 
                                                properties['addresses'])  
                                        print (logMsg)
                                '''
                                
                                
                                logMsg =  "\nCurrent%sHost record %s: %s" % (sameAsZone_Message,absolutename, 
                                        properties['addresses'])  
                                print (logMsg)
                                BAM.bam_logout(bam)
                                return(0)
                                           
                        else: # of if ip_match = True: (#ip_match == False:)
                            logMsg = "Failure: IP %s not found.%shost record %s" % (rdata, sameAsZone_Message, absolutename )
                            print_log.go(log_error, logMsg)
                            '''
                            if debug:
                                if total_ip_count != 1:
                                    logMsg =  "\nDebug:%srecord %s: %s" % (sameAsZone_Message,absolutename, 
                                        properties['addresses'])  
                                    print (logMsg)
                            '''
                            logMsg =  "\nCurrent%sHost record %s: %s" % (sameAsZone_Message,absolutename, 
                                properties['addresses'])  
                            print (logMsg)
                        #endof if ip_match == True:   # ip found, delete it from address list
                #end if zone:
            #end if view:
        #end if configuration:
    except ValueError as e:     # except fosr any api error
        logMsg = "%s" % ( str(e) )
        print_log.go(log_error, logMsg)
        BAM.bam_logout(bam) 
        return(1)
    
    BAM.bam_logout(bam)
    return(0)

    
# ---------------------------------------------------------------------
# start
# ---------------------------------------------------------------------
if __name__ == '__main__':
    host_delete_one()
