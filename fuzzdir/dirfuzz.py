# -*- coding:utf-8 -*-
import base64
import os
import random
import sys
import threading
import time
from optparse import OptionParser
import requests

from TaskCenter import TaskStatus, TaskCenter
from common.initsql import SQL3
from pool.thread_pool import ThreadPool
from ProbeTool import HttpWeb
from common.db.sqlite3_db import sqlite3_db
from common.logger.log_util import LogUtil as logging
from urlparse import urljoin
logger = logging.getLogger(__name__)
mu = threading.Lock()

class DirFuzz(object):

    def __init__(self,taskid=None,assetid=None,dbname=None,url=None,statusqueue=None):
        self.dbname = dbname
        self.taskid = taskid
        self.assetid = assetid
        self.filename = []
        self.fuzzdb = None
        self.url = url
        self.statusqueue = statusqueue
        self.taskrun = False
        self.finished = False
        self.single = False if not self.url else True

    def init_db(self):
        if not self.taskrun:
            if self.single:
                self.fuzzdb = os.path.join(os.path.dirname(__file__),'..','repertory','tmp',"{0}.fuzz.db".format(time.strftime("%Y-%m-%d_%H_%M_%S", time.localtime())))
            else:
                self.fuzzdb = os.path.join(os.path.dirname(__file__),'..','repertory',format(time.strftime("%Y-%m-%d", time.localtime())),"{0}.fuzz.db".format(time.strftime("%H_%M_%S", time.localtime())))
        else:
            self.fuzzdb = os.path.join(os.path.dirname(__file__), '..', 'repertory',format(time.strftime("%Y-%m-%d", time.localtime())),"{0}.fuzz.db".format(time.strftime("%H_%M_%S", time.localtime())))

        if not os.path.exists(os.path.dirname(self.fuzzdb)):
            os.makedirs(os.path.dirname(self.fuzzdb))
        self.fuzzdb = sqlite3_db(self.fuzzdb)
        self.fuzzdb.create_table(SQL3)
        logger.info("database (fuzz.db) initialization completed")

    def init_dir_dict(self):
        filename = os.path.join(os.path.join(os.path.dirname(__file__), 'dict'),"directory.test.lst")
        with open(filename,"rb+") as file:
            self.filename = [x.strip() for x in file.readlines()]

    def cache_content(self,url):
        try:
            filename = "".join(random.sample('abcdefghijklmnopqrstuvwxyz0123456789', 6)) + ".css"
            dirname = "".join(random.sample('abcdefghijklmnopqrstuvwxyz0123456789', 6)) + "/"
            res1 = requests.get(urljoin(url,filename), verify=False, allow_redirects=True, timeout=1)
            res2 = requests.get(urljoin(url, dirname), verify=False, allow_redirects=True, timeout=1)
            res3 = requests.get(url, verify=False, allow_redirects=True, timeout=1)
            content = res3.content
            rs_one = {"taskid": self.taskid, "assetid": self.assetid, "url": url,"banner": base64.b64encode(content[0:100]), "reslength": len(content), "status": 1}
            self.fuzzdb.insert('fuzztask', rs_one, filter=False)
            rs = [res1.content,res2.content,res3.content]
        except:
            rs = None
        return rs

    def req_ad_file(self,url,filename,cache):
        newurl = urljoin(url,filename)
        try:
            res = requests.get(newurl, verify=False, allow_redirects=True, timeout=2)
            condition1 = (abs(len(res.content)-len(cache[0])) <=20) or (abs(len(res.content)-len(cache[1])) <= 20) or (abs(len(res.content)-len(cache[2])) <= 20)
            condition2 = (res.status_code !=405) and ((res.status_code >= 400 and res.status_code < 500) or (res.status_code > 500) or (res.status_code < 200))
            if condition2:
                pass
            else:
                if not condition1:
                    if mu.acquire():
                        content = res.content
                        rs_one = {"taskid":self.taskid,"assetid":self.assetid,"url":newurl,"banner":base64.b64encode(content[0:100]),"reslength":len(content),"status":1}
                        self.fuzzdb.insert('fuzztask', rs_one, filter=False)
                        mu.release()
        except:
            pass

    def result_unique(self):
        rs = self.fuzzdb.queryall("select * from (select *,count(reslength) as flag from fuzztask where taskid={0} and assetid={1} group by reslength) where flag=1".format(self.taskid,self.assetid))
        sql_1 = "delete from fuzztask"
        sql_2 = "update sqlite_sequence SET seq = 0 where name ='fuzztask'"
        self.fuzzdb.query(sql_1)
        self.fuzzdb.query(sql_2)
        for id,taskid,assetid,url,banner,reslength,status,count in rs:
            rs_one = {"taskid": taskid, "assetid": assetid, "url": url,"banner": banner, "reslength": reslength, "status": 1}
            self.fuzzdb.insert('fuzztask', rs_one, filter=False)
            logger.info("url:{0} ".format(url))

    def funzz(self,msgqueue=None):
        if msgqueue:
            self.taskrun = True
        self.init_db()
        self.init_dir_dict()
        tp = ThreadPool(10)
        if msgqueue is None:
            if not self.single:
                rs = self.assetdb.query_all("select * from asset")
                for id, taskid,ip, port, domain, banner, protocol, service, assettype, position, schema in rs:
                    web_banner, web_service, ostype, assettype, domain, position, proext = HttpWeb.detect(ip, port)
                    if proext:
                        url = "{schema}://{ip}:{port}".format(schema=proext,ip=ip,port=port)
                        rs = self.cache_content(url)
                        if rs:
                            for x in self.filename:
                                tp.add_task(self.req_ad_file,url,x,rs)
            else:
                rs = self.cache_content(self.url)
                for x in self.filename:
                    tp.add_task(self.req_ad_file, self.url, x, rs)
        else:
            task_null_count = 0
            while not self.finished:
                time.sleep(0.2)
                if  task_null_count >= 5:
                    self.finished = True
                    continue
                if not msgqueue.empty():
                    rs_one = msgqueue.get(True)
                    self.taskid = rs_one.get("taskid")
                    self.assetid = rs_one.get("assetid")
                    web_banner, web_service, ostype, assettype, domain, position, proext = HttpWeb.detect(rs_one.get("ip"), rs_one.get("port"))
                    if proext:
                        url = "{schema}://{ip}:{port}".format(schema=proext, ip=rs_one.get("ip"), port=rs_one.get("port"))
                        rs = self.cache_content(url)
                        if rs:
                            for x in self.filename:
                                tp.add_task(self.req_ad_file, url, x, rs)
                else:
                    if TaskCenter.task_is_finished(self.statusqueue,"portscan"):
                        task_null_count = task_null_count+1
                        time.sleep(0.5)
                        TaskCenter.update_task_status(self.statusqueue,"dirscan",TaskStatus.FINISHED)
        tp.wait_all_complete()
        self.result_unique()

if __name__ == "__main__":
    optparser = OptionParser()
    optparser.add_option("-t", "--taskid", dest="taskid", type="int", default=-100, help="task's id")
    optparser.add_option("-a", "--assetid", dest="assetid", type="int", default=-100, help="asset's id")
    optparser.add_option("-d", "--dbname", dest="dbname", type="string", default="", help="port scan result's db")
    optparser.add_option("-u", "--url", dest="url", type="string", default="", help="url cues")
    try:
        (options, args) = optparser.parse_args()
    except Exception, err:
        sys.exit(0)
    if len(sys.argv) < 2:
        optparser.print_help()
        sys.exit(0)
    dbname = options.dbname
    taskid = options.taskid
    assetid = options.assetid
    url = options.url
    test = DirFuzz(taskid=taskid,assetid=assetid,dbname=dbname,url=url)
    test.funzz()