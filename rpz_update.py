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
# RPZ-Update.py
#
# v3.4-20230828 fixed log does not show in cli.py issue 
# v3.3-20230826 remove dump_rr def cname_add def cname_delete
# v3.2-20230826 fix "pw" issue (moved to top of para check)
# v3.1-20230810 rewrite architecture, login to BAM one time, search obj one time and reused searched obj id to 
#               to increase performancef (speed add from 7 cname/sec to 33 cname/sec in new version)
# v1.1-20211209 remove some space in log
# v1.0-20211208 (use BAM.py # v20211012-G)  : read update CSV (not full csv). ref update.csv
#
#  bamconfig.json   need to be saved in UTF-8 format bacause it contains Chinese characters
#
# 1) usage rpz-update.py
#   python3 rpz-update.py  -i input2.xlsx
#
# 2) how to call cname_add.py
#    python3  cname_add.py -c config1 -v view1 -z test.corp -r '*.google.com"  -i to.rpz.test.corp
#        -c config_name
#         -v view_name
#         -z zone_name
#         -r record_name
#         -i linkedRecordName
#         -k (same as zome record. when -k is used, -r is ignored)
#----------------------------------------------------
# in pervious version, use cname_add.py, cname_delete.py - around 7 cname add per second (in my vm env)
#     1.3M cname will take 51.5 HR (2.1 days) which is too slow
#
#//use cname_add.py, cname_delete.py (need to login everytime, it is slow)
#cname_add.py,
#    login bam
#    use bam.getEntityByName() to search config
#    use bam.getEntityByName() to search view
#    use bam.getEntityByName() to search zone (until locate the rpz.corp)
#    
#    use bam.addAliasRecord() to add record
#        use bam.addAliasRecord( viewid, add_absolutename, linkedRecordName,ttl ,properties)
#            Note: properties = "parentZoneName="+zone   # this is to allow adding rrname has dot 
#                                                              # (e.g. "a1.b1".test.corp)
#    logout bam
#
#cname_delete.py
#    use bam.getEntityByName() to search config
#    use bam.getEntityByName() to search view
#    use bam.getEntityByName() to search zone (until locate the rpz.corp)
#    
#    result_list = bam.getEntitiesByName(zoneid, rrName, "AliasRecord", 0, max_obj_count)
#
#    for ent in result_list:
#        rtn = bam.delete( ent['id'] )        
#    logout bam
#
#------------------------------------------------------



# ------------- module from internet ---------

import getopt
import sys
import json
import os

#import openpyxl
import csv

import ipaddress

# ------------- module by BlueCat ---------
import BAM
#from cname_add import *
#from cname_delete import *
#from dump_rr import *

# ------------- module from internet ---------
import urllib3  # to suppress https cert worning
#urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ---------------------------------------------------------------------
# global var
# ---------------------------------------------------------------------


rpz_go_help = """
python3 rpzUpdate.py -i input.csv
    -n                 # dry-run mode - don't really do add/delete, show commands only
    -z rpz-zone        # update zone [block|blackhole|redirect|whitelist]
    -o [add|delete]    # Operation: add or delete
    -t [domain|ip]     # add/delete "domain name" or "IPv4 IP" to rpz zone (default "domain)
    -i input.csv       # input csv
    -e password_encode # encode the API user's password)

    # Read rpz items from a csv file and add them to a [customized RPZ zone] (### NOT the built-in BAM RPZ function ###)
    #
    # note: (1) upload function will update multiple views defined in bamconfig.json
    #       (2) CSV example:
    #--- domain.csv example ---
    a1.com
    a2.com
    a3.com
    #--- ip.csv example ---
    10.1.1.1
    10.1.1.2
    10.1.1.3
"""


version = "3.4"

ip_sheet_name = 'IP'            # ip sheet name in xlsx
domain_sheet_name = 'Domain'    # domain sheet name in xlsx

domain_flag_column = 4          # add/delete flag in XLSX (starting from 0)
ip_flag_column = 5              # add/delete flag in XLSX (starting from 0)


# to disable exception trackback information (if not set, urllib3 excpetion will be printed to screen)
sys.tracebacklimit = 0
#sys.tracebacklimit = 1000

# ---------------------------------------------------------------------
# main function
# ---------------------------------------------------------------------
def rpz_update(*args):


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
    
    
    
    # ------------- General var setup -------------
    arg_list = []

    # ------------- getop var -------------
    show_version = False
    input_file = ''         # -i input.csv       # input csv
    encode_pw = ''          #  -e password_encode # encode the API user's password)
    rpz_zone = ''           # -z rpz-zone  # update zone [block|blackhole|redirect|whitelist]
    operation = ''          # -o [add|delete]    # Operation: add or delete
    type_of_rpz = 'DOMAIN'  # -t [domain|ip]      

    debug_input = None
    debug = False    
    debug_user = False
    debug_api = False 
    debug_bam = False 
    dry_run = False

    # ---------- var for move bam login, search config, view, zone to master function
    
    # default = 3 sec. If change any  other number, it will overwrite 
    #       REST requests timeout value
    req_timeout = 3

    # read max obj count in API
    max_obj_count = "1000"
    
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
    rrtype = None
    linkedRecordName = None


    confid = 0
    viewid = 0
    zoneid = 0

    sameAsZone = None
    add_absolutename = None


    # ------------------- arg of calling cli function --------------
    # example
    # argument_list =  [confg_flag, config_name, view_flag, view_name, zone_flag, zone_name, rrName_flag ,rrName ]

    # rtn = a_query( *myargument2_list)  
    # need to have a (*) to unpact the tuple (otherwise, in receive function will see one list

    workingDir = ''
    logPath = ''
    logFileName = ''
    
    if os.name == 'nt':
        #  same dir in Windows
        workingDir = "./"
        logPath = "./"
        logFileName = "cli"
    else:
        # Linux platform
        workingDir = "./"
        logPath = "./"
        logFileName = "cli"  # rename use different log name for master file

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
    
    # create a print_log object. (use same output log file in cname_add/delete.py)
    print_log = BAM.print_log( log_prog_type_index ,input_cmd_log, logPath, logFileName)

    # --- load config by BAM.load_config()  return json format "config"    
    configFile = workingDir + "bamconfig.json"
    
    # --- other parameters (e.g. https, pw et) will be checked and print error to log file -----
    config_file = BAM.load_config(print_log, configFile)

    if config_file == 1:   #if config return 1, there's someting wrong in config file
                      # otherwise config should be 'dict'
        #config file read error. Just exit prog
        return (1)
    
    configFile_error = False
    configFile_error_msg = ''
    
    if not 'rpz-block-zone' in config_file or config_file['rpz-block-zone']=='':
        configFile_error_msg += ' "rpz-block-zone"'
        configFile_error = True
    if not 'rpz-redirect-zone' in config_file or config_file['rpz-redirect-zone']=='':
        configFile_error_msg += ' "rpz-redirect-zone"'
        configFile_error = True
    if not 'rpz-blackhole-zone' in config_file or config_file['rpz-blackhole-zone']=='':
        configFile_error_msg += ' "rpz-blackhole-zone"'
        configFile_error = True
    if not 'rpz-whitelist-zone' in config_file or config_file['rpz-whitelist-zone']=='':
        configFile_error_msg += ' "rpz-whitelist-zone"'
        configFile_error = True
    if not 'external-host-record' in config_file  or config_file['external-host-record']=='':
        configFile_error_msg += ' "external-host-record"'
        configFile_error = True
    if not 'config-name' in config_file or config_file['config-name']=='':
        configFile_error_msg += ' "config-name"'
        configFile_error = True
    if not 'view-name' in config_file or config_file['view-name']=='':
        configFile_error_msg += ' "view-name"'
        configFile_error = True
    if not 'add-flag' in config_file or config_file['add-flag']=='':
        configFile_error_msg += ' "add-flag"'
        configFile_error = True
    if not 'delete-flag' in config_file or config_file['delete-flag']=='':
        configFile_error_msg += ' "delete-flag"'
        configFile_error = True
    if configFile_error:        
        logMsg = "Failure: config file format error:%s is required in config file (bamconfig.json)" % ( \
                    configFile_error_msg )
        
        print_log.go(log_error, logMsg)
        return(1)

    # -------------------------------------------------
    # Get login id/pw from config file
    # -------------------------------------------------
    if config_file['https'].upper() == 'TRUE':
        https = True
    else:
        https = False

    # --- get api & apiPw ---
    api = config_file['user']
    apiPw = config_file['password'] 
    
    # decode api verify encrypted password to see if it is valid.
    apiPw_decode = BAM.decrypt_password(apiPw) 
        
    if apiPw_decode == '':
        logMsg = "API user password decode error" 
        print_log.go(log_error, logMsg + passed_args)
        return(1)  

    # -------------------------------------------------
    # var for cname_add script
    # -------------------------------------------------
    rtn=1

    confg_flag = '-c'
    view_flag = '-v'
    zone_flag = '-z'
    rrName_flag = '-r'
    link_flag = '-i'
    
    
    config_name = config_file['config-name']
    
    # view_list is a list
    
    view_list_len = 0
    view_list = config_file['view-name']
    view_list_len = len(view_list)
    
    
    rrName = None   # to be input by xlsx
    link_to_host = config_file['external-host-record']
    
    # var for dump_rr
    rr_type_item = ''
    rrType_flag = '-t'      # used in dump_rr.py
    print_it_flag = '-n'    # # used in dump_rr.py -n : not print to screen
    dump_all_flag = '-a'    # used in dump_rr.py
    
    rr_count_before = 0
    rr_count_after = 0
    
    
    print_to_screen = False
    ip_rpz = ''
    
    
    # ---------------------------------------------------------
    # read from CLI
    # ---------------------------------------------------------
    input_args = list(args)   # args is the arguments passed by calling this function.

    try:
        # this is to prepare if this script is called by other python script.
        if len(input_args)!=0:    #this is called by other python script
            opts, args = getopt.getopt(input_args, "dni:z:t:o:e:p:h", ["debug=","version"])  
        else: # call this script from CLI. Parsing "sys.argv[1:]" ([1:] - not include script name)
            opts, args = getopt.getopt(sys.argv[1:], "dni:z:t:o:e:p:h", ["debug=","version"])
    except getopt.GetoptError as e: 
        logMsg = str(e)
        print_log.go(log_error, logMsg )
        return(1) 

    for o,v in opts:
        if o == "-d": debug = True 
        elif o == "-n": dry_run = True 
        elif o == "-i": input_file = v
        elif o == "-z": rpz_zone = v
        elif o == "-t": type_of_rpz = v
        elif o == "-o": operation = v
        elif o == "-e": encode_pw = v
        elif o == "-p": print_to_screen = v
        elif o == "--version": show_version = True
        elif o == "--debug": debug_input = v  
        elif o == "-h":
            print (rpz_go_help)
            return(0)
    if not opts:
        print (rpz_go_help)     # print help screen
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
    # cli parameters 
    # ---------------------------------------------------------
    
    # pw need to be at top position of para check
    if encode_pw != '':
        if (encode_pw[0:1] == "-"):
            logMsg = "Failure: -e encrypt_pw option is required" 
            print_log.go(log_error, logMsg)
            return(1)
        else:
            print('Please put the following encoded api user password in config file:')
            print(BAM.encrypt_password (encode_pw))
            return (0)
    
    if input_file != '':
        if input_file[0:1] == "-":
            logMsg = "Failure: -i input file option is required" 
            print_log.go(log_error, logMsg)
            return(1)
    else: # is empty
        logMsg = "Failure: -i input file option is required" 
        print_log.go(log_error, logMsg)
        return(1)
    
    if rpz_zone != '':
        if rpz_zone[0:1] == "-":
            logMsg = "Failure: -z rpz_zone option is required" 
            print_log.go(log_error, logMsg)
            return(1)
        else:
            # [block|blackhole|redirect|whitelist]
            valid_input = ["BLOCK","BLACKHOLE", "REDIRECT", "WHITELIST"]
            rpz_zone = rpz_zone.upper()
            if not (rpz_zone in valid_input):
                logMsg = "Failure: -z rpz_zone option needs to be [block|blackhole|redirect|whitelist]" 
                print_log.go(log_error, logMsg)
                return(1)
    else: # is empty
        logMsg = "Failure: -z rpz_zone option is required" 
        print_log.go(log_error, logMsg)
        return(1)

    if type_of_rpz != '':
        if type_of_rpz[0:1] == "-":
            logMsg = "Failure: -t type option is required" 
            print_log.go(log_error, logMsg)
            return(1)
        else:
            # [domain|ip]
            valid_input = ["DOMAIN","IP"]
            type_of_rpz = type_of_rpz.upper()
            if not (type_of_rpz in valid_input):
                logMsg = "Failure: -t type needs to be [domain|ip]" 
                print_log.go(log_error, logMsg)
                return(1)
    else: # is empty, set to domain if -t is not given
        type_of_rpz = 'DOMAIN'

    if operation != '':
        if operation[0:1] == "-":
            logMsg = "Failure: -o operation option is required" 
            print_log.go(log_error, logMsg)
            return(1)
        else:
            # [add|delete]
            valid_input = ["ADD","DELETE"]
            operation = operation.upper()
            if not (operation in valid_input):
                logMsg = "Failure: -o operation option needs to be [add|delete]" 
                print_log.go(log_error, logMsg)
                return(1)
    else: # is empty
        logMsg = "Failure: -o roperation option is required" 
        print_log.go(log_error, logMsg)
        return(1)
    
    if show_version == True:
        print("Version %s" % version)
        return(0)


    # ---------------------------------------------------------
    # setup rpz_zone
    # ---------------------------------------------------------
    if rpz_zone == "BLOCK":
        zone_name = config_file['rpz-block-zone']
    elif rpz_zone == "BLACKHOLE":
        zone_name = config_file['rpz-blackhole-zone']
    elif rpz_zone == "REDIRECT":
        zone_name = config_file['rpz-redirect-zone']
    elif rpz_zone == "WHITELIST":
        zone_name = config_file['rpz-whitelist-zone']
    else: #shoud not happen
        zone_name = ''



    configuration = config_file['config-name']
    view_list = config_file['view-name']
    zone = zone_name
    
    link_to_host = config_file['external-host-record']

    # ---------------------------------------------------------
    # dump RR from target zone to get total number of records
    # ---------------------------------------------------------
    #arg_list = []
    #arg_list =  [confg_flag, config_name, view_flag, view_name, zone_flag, zone_name, 
    #        rrType_flag, rr_type_item, print_it_flag, dump_all_flag ]
    
    

    # ---------------------------------------------------------
    # test csv if it exists
    # ---------------------------------------------------------
    if not os.path.isfile(input_file):
        logMsg = " Error: %s file not exist" % input_file
        print_log.go(log_error, logMsg)
        return(1)    

    # ---------------------------------------------------------
    # login BAM
    # ---------------------------------------------------------
    if https:
        BAM_URL = "https://" + config_file['hostname'] + "/Services/REST/v1/"
    else:
        BAM_URL = "http://" + config_file['hostname'] + "/Services/REST/v1/"       
    try:                   
        bam=BAM.BAM( BAM_URL, req_timeout)       
        response = bam.login( api, apiPw_decode )   #response.ok is checked in bam.login()
    except Exception as e:  # except of login()
        logMsg = bam.mask_id_pw( str(e) )  # mask username and pw in e when login fail
        print_log.go(log_error, logMsg)
        return(1)    



    # ---------------------------------------------------------
    # open csv and read data //todo test input_file before login to bam
    # ---------------------------------------------------------
    
    # data is the csv input 
    data=[]
    total_row = 0
    
    if os.path.isfile(input_file):
        with open(input_file, mode='r') as csv_file:
            csv_reader = csv.reader(csv_file)           
            for row in csv_reader:
                if row: #skipe empty row (return True if row is NOT an empty list)
                    data.append(row[0])
    else:
        print (" Error: %s file not exist" % input_file )
        return (1)

    if debug_api:
        print('[--- debug: input list read from csv (skipped empty row) ---]')
        print(data)

    # total row of csv files
    total_row = len(data)


    # ----------------------------------------------------------------
    # get config/view/zone entity id
    # ----------------------------------------------------------------
    err_msg = ''
    
    #print(view_list)
    
    data_add_count = 0

    try:

        if configuration:
            config_ent = bam.getEntityByName("0", configuration, "Configuration")
            confid = config_ent['id']
            if confid == 0:
                logMsg = "Failure: Failed to get configuration: %s" % (configuration)
                if print_to_screen:
                    print_log.go(log_error, logMsg)
                else:
                    print_log.log_only(log_error, logMsg)
                return (1) # error, no such config, just exit program

        # loop through each view
        for view in view_list:
            if view:
                view_ent = bam.getEntityByName(confid, view, "View")
                viewid = view_ent['id']
                if viewid == 0:
                    logMsg = "Failure: Failed to get view: %s" % (view)
                    print_log.go(log_error, logMsg)
                    continue
                    
                #for cname_add, get zoneid is not required. ### //todo
                if zone: 
                    zone_ent = bam.find_zone(viewid, zone)
                    zoneid = zone_ent['id']
                    if zoneid == 0:
                        logMsg = "Failure: Failed to get zone: %s" % (zone)  
                        print_log.go(log_error, logMsg)
                        continue
                    # ------------------------------------------------ 
                    # End of read config/view/zone 
                    # ------------------------------------------------ 
                        
        
            # ---------------------------------------------------------
            # process data in CSV
            # ---------------------------------------------------------
            # data[] has the list to be add/delete (empty row is skipped)
            
            for item in data:
            
                if type_of_rpz == "DOMAIN": # need to build ip fqdn 
                    item_final = item
                
                else: # type_of_rpz == "IP"
                
                    ip_rpz = ''
                    
                    try:
                        ip_object = ipaddress.ip_address(item)
                    except ValueError: #if "item" is not an valid IPv4 IP
                        logMsg = "Error: %s is not a valid IP address %s, %s, %s)" % (item, config_name, 
                            view, zone_name)
                        print_log.go(log_error, logMsg)
                        continue #jump to for item in data:
                        
                    # item is an valid IPv4 IP. Start to build rpz required format
                    tmp = str(item).split(".")

                    if len(tmp) == 4: # only IPv4 is supported
                        ip_rpz = "32." + tmp[3] + "." + tmp[2] + "." + tmp[1] + "." + tmp[0]+".rpz-ip"
            
                    item_final = ip_rpz
                    
                #endof if type_of_rpz == "DOMAIN": # need to build ip fqdn 
                
                # item_final is the fqdn to be added/deleted (no matter it is IP or domain name)
                
                if operation == "ADD":
                    try:
                        rrName = item_final
                        absolutename = rrName + "." + zone
                        linkedRecordName = link_to_host
                        ttl = "-1"
                        properties = "parentZoneName="+zone   # this is to allow adding rrname has dot 
                                                              # (e.g. "a1.b1".test.corp)
                        # print sent argument (debug only)
                        #print( viewid, absolutename, linkedRecordName, ttl ,properties)
                        
                        if dry_run:
                            logMsg = "dry-run: add view:%s record:%s linkedRecordName:%s" % (
                                view, absolutename, linkedRecordName)
                            print_log.go(log_info, logMsg)
                            data_add_count += 1
                        else:
                            ent_id = bam.addAliasRecord( viewid, absolutename, linkedRecordName,
                                                            ttl ,properties)
                            logMsg = "Success: added view:%s record:%s linkedRecordName:%s" % (
                                view, absolutename, linkedRecordName)
                            print_log.go(log_info, logMsg)
                            data_add_count += 1
                                              
                    except ValueError as e:
                        logMsg = "Failure: %s Failed to add view: %s record:%s linkedRecordName:%s" % ( 
                            str(e), view, absolutename, linkedRecordName )
                        print_log.go(log_error, logMsg)
                        continue # goto loop. continue to do next RR
                            
                else: # operation == "DELETE":

                    rrName = item_final
                    absolutename = rrName + "." + zone
                    linkedRecordName = link_to_host
                    ttl = "-1"
                    properties = "parentZoneName="+zone   # this is to allow adding rrname has dot 
                                                          # (e.g. "a1.b1".test.corp)
                    
                    if dry_run:
                        logMsg = "dry-run: add view:%s record:%s linkedRecordName:%s" % (
                            view, absolutename, linkedRecordName)
                        print_log.go(log_info, logMsg)
                        data_add_count += 1
                    else:
                        # search the rr first
                        try:
                            result_list = bam.getEntitiesByName(zoneid, rrName, "AliasRecord", 0, max_obj_count)
                        except ValueError as e:
                            logMsg = "Failure: %s fail to get record" % str(e)
                            print_log.go(log_error, logMsg)
                            continue # goto loop. continue to do next RR
                            
            
                        if len(result_list) == 0: # no entity found
                            logMsg = "Failure: NO record found! view:%s record:%s linkedRecordName:%s" % (
                                view, absolutename, linkedRecordName)
                            print_log.go(log_error, logMsg)
                            
                        else: # found entity. compare rdata for same record type
                            for ent in result_list:
                                properties = bam.splitProp(ent)
                                
                                if debug_api:
                                    print(ent)
                                    print(properties)
                                    
                                    # {'id': 172939, 'name': '*.google.com', 'type': 'AliasRecord', 
                                    # 'properties': 'absoluteName=*.google.com.block.rpz.test.corp|
                                    #                linkedRecordName=to.rpz.test.corp|' }
                                try:
                                    rtn = bam.delete( ent['id'] )

                                    logMsg = "Success: deleted view:%s record:%s linkedRecordName:%s" % (
                                        view, absolutename, linkedRecordName)
                                    print_log.go(log_info, logMsg)
                                    data_add_count += 1
                                    
                                except ValueError as e:
                                    logMsg = "Failure: %s Failed to add view: %s record:%s linkedRecordName:%s" % ( 
                                        str(e), view, absolutename, linkedRecordName )
                                    print_log.go(log_error, logMsg)
                                    continue # goto loop. continue to do next RR
                                                                        
                #endof if operation == "ADD":
            #endof for item in data:
        #endof for view in view_list:
                    
    
    except ValueError as e:     # except fosr any api error
        logMsg = "%s" % ( str(e) )
        print_log.go(log_error, logMsg)
        BAM.bam_logout(bam) 
        return (1)
    
    # endof for view in view_list:
    total_todo = total_row * view_list_len
    logMsg = "Total rows in CSV files:%s processed items:%s (total views:%s. total_row*total_view= %s)" % (
        total_row, data_add_count, view_list_len, total_todo)
    print(logMsg)
    
    return(0)

# ---------------------------------------------------------------------
# main()
# ---------------------------------------------------------------------
if __name__ == '__main__':

    rpz_update()
    
    
    
    
