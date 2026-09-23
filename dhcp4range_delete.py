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
# program name: dhcp4range_delete.py
# by: Eric Chen (hchen@bluecatnetworks.com)
# python ver: python 3
# BAM ver: 26.1
#
# v1.0-20260918 created (same style as dhcp4range_add.py)
#


'''
dhcp4range_delete -c config1 -i 10.1.1.0/24 -s 10.1.1.11 -e 10.1.1.20
     -c config1                 # config name e.g. config1
     -i ip4network/subnet       # ipv4 network e.g. 10.1.1.0/24
     -s start_ip                # start ip e.g. 10.1.1.11
     -e end_ip                  # end ip e.g. 10.1.1.20

     # delete a dhcpv4 range from a network
'''

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
version = "1.0"

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
# convertRR = False | False //whether to convert Resource Record (RR) to lower cases
#-------------------------------------------
convertRR = False

# ---------------------------------------------------------------------
# main function
# ---------------------------------------------------------------------
def dhcp4range_delete(*args):
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
    logMsg2 = ''        # for query script to build multiple result
    cmdLine = ''
    input_cmd = ''
    input_cmd_log = ''

    api = ''
    apiPw = ''
    apiPw_decode = ''
    https = False

    configuration = None
    show_version = False

    confid = 0

    # ---------------------------------------------------
    ipNetwork = ''

    type = "IP4Network"

    start = 0
    count = 10000

    start_ip = ''
    end_ip = ''
    # ---------------------------------------------------

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

    # -------------------------------------------------
    # 20240921- fix arg empty problem
    # -------------------------------------------------
    i=0
    for foo in input_args:
        if foo == '':
            del input_args[i]       #delete item (vaule = ''). e.g. -y is not given
        i=i+1
    # -------------------------------------------------
    # end fo fix arg empty problem
    # -------------------------------------------------

    try:
        # this is to prepare if this script is called by other python script.
        if len(input_args)!=0:    #this is called by other python script
            opts, args = getopt.getopt(  input_args, "dc:i:s:e:h",["debug=","version"])
        else: # call this script from CLI. Parsing "sys.argv[1:]" ([1:] - not include script name)
            opts, args = getopt.getopt(sys.argv[1:], "dc:i:s:e:h",["debug=","version"])
    except getopt.GetoptError as e:
        logMsg = str(e)
        print_log.go(log_error, logMsg)
        return(1)

    for o,v in opts:
        if o == "-d": debug = True
        elif o == "-c": configuration = v
        elif o == "-i": ipNetwork = v
        elif o == "-s": start_ip = v
        elif o == "-e": end_ip = v
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

    if debug_api:
        print ("--------------[debug: input parameter] ---------------")
        print(opts)
        print("")

    # ---------------------------------------------------------
    # test cli required parameters
    # ---------------------------------------------------------
    if (not configuration) or (configuration[0:1] == "-"):
        logMsg = "Failure: -c config option is required"
        print_log.go(log_error, logMsg)
        return(1)
    if (not ipNetwork) or (ipNetwork[0:1] == "-"):
        logMsg = "Failure: -i ipNetwork option is required"
        print_log.go(log_error, logMsg)
        return(1)
    if (not start_ip) or (start_ip[0:1] == "-"):
        logMsg = "Failure: -s start_ip option is required"
        print_log.go(log_error, logMsg)
        return(1)
    if (not end_ip) or (end_ip[0:1] == "-"):
        logMsg = "Failure: -e end_ip option is required"
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
    # get config
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
            else:
                # ent found, but need to tell whether it is in same config!!!
                try:
                    # type = "IP4Network"
                    result_list = bam.searchByObjectTypes( ipNetwork, type, start, count)
                except ValueError as e:
                    logMsg = "Failure: %s fail to get record" % str(e)
                    print_log.go(log_error, logMsg)
                    BAM.bam_logout(bam)
                    return(1)

                if len(result_list) == 0: # no entity found
                    logMsg = "Failure: IP4Network %s is not found!" % ipNetwork
                    print_log.go(log_error, logMsg)

                else: # found entity

                    #return only object's parent config id  == configid. The object will be save in ent_rtn
                    ent_rtn = filter( lambda ent: bam.getConfiguration(ent['id']) == confid, result_list )

                    ent_list= list(ent_rtn) #convert ent_rtn(filter object) to list

                    if debug_api:
                        print ('---------------- debug: Entity read ----------')
                        print (ent_list)
                        print ('Found obj count: %s' %  len(ent_list) )

                    if len(ent_list) > 1:
                        logMsg = "Failure: %s get more than one object. Exit program" % ipNetwork
                        print_log.go(log_error, logMsg)
                        BAM.bam_logout(bam)
                        return(1)

                    ent = ent_list[0]  # note ent_list should be only one element now (our target obj)
                    network_id = ent['id']

                    try:
                        range_ent = bam.getEntityByRange(network_id, start_ip, end_ip, "DHCP4Range")

                        if debug_api:
                            print('---[debug: range_ent -----------------')
                            print(range_ent)

                    except ValueError as e:
                        logMsg = "Failure: %s fail to get dhcp v4 range" % str(e)
                        print_log.go(log_error, logMsg)
                        BAM.bam_logout(bam)
                        return(1)

                    if range_ent['id'] == 0: # no entity found
                        logMsg = "Failure: dhcp v4 range %s-%s not found in network %s" % (
                                start_ip, end_ip, ipNetwork)
                        print_log.go(log_error, logMsg)

                    else: # found range_ent
                        try:
                            bam.delete(range_ent['id'])

                            logMsg = "Success: deleted dhcp v4 Range. Network: %s Range: %s-%s" % (
                                    ipNetwork, start_ip, end_ip)
                            print_log.go(log_info, logMsg )

                        except ValueError as e:     # except fosr any api error
                            logMsg = "%s" % ( str(e) )
                            print_log.go(log_error, logMsg)
                            BAM.bam_logout(bam)
                            return(1)

                return(1)

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
    dhcp4range_delete()
