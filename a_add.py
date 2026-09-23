#!/usr/bin/python
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
# v5.6-2023-828 fixed log does not show in cli.py issue 
# v5.5-20230827 update help
# v5.4-20221209
#       1) modified: logPath = "./"
#       2) add flag convertRR = False to convert RR Name, rdata to lower cases.
# v5.3-20220221 update BAM.bam_logout(bam) before all return()
# v5.2 allow enter rrname with dot
# v5.1 use BAM.py v20210918-1735
# v4.2 2021/8/1 use new BAM.get_confid(), BAM.get_viewid(), BAM.get_zoneid()
# v4.0 2021/7/8 use new BAM.py (created by Eric Chen) 
#       - modify to work with python 3
#       - use bam.find_zone() instead of split fqdn loop search
#       - use print_log class in BAM.py

'''
a-add -c config1 -v view1 -z test.corp -r pc1 -i 10.10.10.3
a-add -c config1 -v view1 -z test.corp -i 10.10.10.3 -k

    -c config_name
    -v view_name
    -z zone_name
    -r record_name
    -i IP
    -k same as zome record (when -k is used, -r is ignored)

    # Add an A record to a zone 
'''

# ------------- module from internet ---------

import getopt
import sys
import json
import os

# ------------- module by BlueCat ---------
import BAM

# ------------- module from internet ---------
import urllib3  # to suppress https cert worning
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ---------------------------------------------------------------------
# global var
# ---------------------------------------------------------------------
version = "5.6"

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
def a_add(*args): 
    
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
    # local var setup
    # ---------------------------------------------------------------------

    logMsg = ''
    cmdLine = ''
    input_cmd = ''
    input_cmd_log = ''

    api=''
    apiPw=''
    apiPw_decode = ''
    https=False
    
    configuration = None
    view = None
    zone = None
    rrName = None
    rdata = None
    matchclient = None
    user = None
    type = None

    show_version = False

    # ------------------------------------------ for debug
    debug = False           # -d of getopt() 
    debug_input = None      # input (type str) of getopt()
    
    debug_user = False
    debug_api  = False
    debug_bam  = False

    confid = 0
    viewid = 0
    zoneid = 0

    sameAsZone = None
    add_absolutename = None

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


    # --- load config by BAM.load_config()  return json format "config"
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
                              # use new var just because getopt() also use "args" as output

    try:
        # this is to prepare if this script is called by other python script.
        if len(input_args)!=0:    #this is called by other python script
            opts, args = getopt.getopt(input_args, "qndc:v:z:r:i:kh" , ["debug=","version"])            
        else: # call this script from CLI. Parsing "sys.argv[1:]" ([1:] - not include script name)
            opts, args = getopt.getopt(sys.argv[1:], "qndc:v:z:r:i:kh" , ["debug=","version"])
            
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
        elif o == "-k": sameAsZone = True 
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
        debug_user = True    
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
        
    # note: sys.tracebacklimit = 0 
    #       This is to disable exception trackback information (if not set, 
    #       urllib3 excpetion will be printed to screen)
    # the # default value = 1000
    
    if debug_api:
        print("---[debug: passed arguments] ----")
        print(opts)
        print("")
    
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

    # note - issue: found -c config1 -v view1 -z test.corp  -i 10.10.104 -r -k
    # will cause sameAsZone=None (because "-K" become -r's parameter. (rrName=="-k")
    # this is issue of getopt

    if sameAsZone:
        sameAsZone_Message = " SAME AS ZONE "
    else:
        sameAsZone_Message = " "

    if not rdata: 
        if (rdata == None) or (rdata[0:1] == "-"):
            logMsg = "Failure: -i data option is required"
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
                return (1)
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
                        # this is to meet API add same as zone record requirement e.g. need ".test.corp"
                        add_absolutename = "."+absolutename
                    else:
                        absolutename = rrName + "." + zone
                        add_absolutename = absolutename
                        properties = ""
                    try:
                        type = "A"
                        ttl = "-1"
                        properties = "parentZoneName="+zone # this is to allow adding rrname has dot (e.g. "a1.b1".test.corp)

                        # ---- host record only ----
                        # properties = "parentZoneName="+zone+"|reverseRecord=false|"

                        # ---- add record (arg example)----
                        # response = bam.addGenericRecord( "100913", "a1.test.corp", "A", "1.1.1.14","-1","")
                        
                        rtn_id = bam.addGenericRecord( viewid, add_absolutename, type, rdata,ttl,properties)

                        if rtn_id != 0:     # f status_code is less than 200
                            logMsg = f"Success: added{sameAsZone_Message}record {absolutename} Rdata: {rdata} (id:{rtn_id})"
                            print_log.go(log_info, logMsg)
                        else:
                            # this session should not be run. if not 200 OK, should go to except.
                            # don't know what sitaution will cause rtn_id == 0?
                            
                            # we don't have the response.text. it will be in raised err.
                            
                            logMsg = "Failure: Failed to add%srecord %s" % ( sameAsZone_Message, absolutename)
                            print_log.go(log_error, logMsg)
                            BAM.bam_logout(bam)
                            return(1)
                            
                    except ValueError as e:
                        logMsg = "Failure: %s Failed to add%srecord %s" % ( str(e), 
                                sameAsZone_Message, absolutename)
                        print_log.go(log_error, logMsg)
                        BAM.bam_logout(bam) 
                        return(1)

                    # add success
                    BAM.bam_logout(bam)
                    return(0)
                    
                #endof if zone:
            #endof if view:
        #endof if configuration:
        
    except ValueError as e:     # except fosr any api error
        logMsg = "%s" % ( str(e) )
        print_log.go(log_error, logMsg)
        BAM.bam_logout(bam) 
        return(1)
        
# ---------------------------------------------------------------------
# main()
# ---------------------------------------------------------------------
if __name__ == '__main__':
    a_add()
    
