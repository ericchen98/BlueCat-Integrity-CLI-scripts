#!/usr/bin/env python
# coding=UTF-8
#
# ver: 0.7 : Eden modify the file name to meet 4A requirment. (add "vDNS-" in the follow command
#             fileHandler = logging.handlers.WatchedFileHandler("{0}/vDNS-{1}".format(logPath, fileName))
# ver: 0.6 : use v0.4, use one ogger to file, "print" command to console
#            log opType is handle at each script 
# ver: 0.4 : To meet 4A requirement, add, del, view need to be added. It will be handle by each program
# ver: 0.3 : add  ssh client IP and user id
# ver: 0.2 : use logging.handlers.WatchedFileHandler to work with Linux rotate (allow log file be closed & openned)
# ver: 0.1 : use logging.FileHandler to work with Linux rotate

import logging
import logging.handlers
import os
import sys
import getpass


def getLogger():

    logPath = None
    fileName = None
    ssh_connection = None
    ssh_client_ip = None
    userid = None
    
    if os.name == 'nt':
        # write cli.log to same dir in Windows (file name will be cli.csv - to meet 4A requirement)
        logPath = "./"
        fileName = "cli" 
        ssh_client_ip = ''
    else:
        # Linux platform
        logPath = "./"
        fileName = "cli"    # the file name will be cli.csv

        # for linux, get ssh client IP
        ssh_connection = os.getenv("SSH_CONNECTION")
        
        # need to makesure ssh_connection != None before call .split()
        if ssh_connection != None:
            ssh_connection = os.getenv("SSH_CONNECTION").split()
            ssh_client_ip = ssh_connection[0]
        else:
            #ssh_connection is None, this might be not ssh or run su - bluecat after ssh
            ssh_client_ip = ''
    # end if os.name == 'nt':
    
    userid = getpass.getuser()    

    # get current user for log
    if userid == None:
        userid == ''
            
    
    # create obj rootLogger
    logger = logging.getLogger()

    #set display level
    logger.setLevel(logging.DEBUG)
    fileHandler = logging.handlers.WatchedFileHandler("{0}/vDNS-{1}".format(logPath, fileName))
    
    #logtime,subuser,appname,sip,appmodule,optype,optext
    # optype? give CLI?
    #
    # config log formatter
    # formatterString="%(asctime)s,%(name)s,vDNS,{0},cli,other,[%(levelname)s] : %(message)s".format(ssh_client_ip)
    # add ssh_userid
    # formatterString="%(asctime)s,{0},vDNS,{1},cli,other,[%(levelname)s] : %(message)s".format(userid, ssh_client_ip)
    
    
    formatterString="%(asctime)s,{0},vDNS,{1},cli,%(message)s".format(userid, ssh_client_ip)
    
    logFormatter = logging.Formatter(formatterString,"%Y-%m-%d %H:%M:%S")

    fileHandler.setFormatter(logFormatter)

    # add first log Handler (to log file)
    logger.addHandler(fileHandler)

    # config consoleHander (to print to stdout)
    # v0.6 remark this don't print to console. Use print in script to print message as console needs different message

    #   consoleHandler = logging.StreamHandler()
    #   logger.addHandler(consoleHandler)

    return logger
