#!/usr/bin/env python3
import sys
import logging
import json
from time import sleep, time
from hashlib import sha256 as _sha256
from .daemon import DaemonThread
from .test_framework.authproxy import JSONRPCException
from .messenger_factory import MessengerFactory
from .connectivity import getelementsd
from .inflation import Inflation

BLOCK_TIME_DEFAULT = 60
REDEEM_SCRIPT = '' # This is the blocksignscript's redeemscript aka block witnessscript. Unique to each network.
WALLET_PASS_PHRASE = ''

def round_time(period, time):
    time_mod = time % period
    if time_mod == 0:
        return time
    if time_mod >= period / 2:
        return time - time_mod + period
    return time - time_mod

class BlockSigning(DaemonThread):
    def __init__(self, conf, nodes, in_rate, in_period, in_address, script, signer=None):
        super().__init__()
        self.conf = conf
        self.elementsd = getelementsd(self.conf)
        self.default_interval = BLOCK_TIME_DEFAULT if "blocktime" not in conf else conf["blocktime"]
        self.default_redeem_script = REDEEM_SCRIPT if "redeemscript" not in conf else conf["redeemscript"]
        self.wallet_pass_phrase = WALLET_PASS_PHRASE if "walletpassphrase" not in conf else conf["walletpassphrase"]
        self.catchup_interval = self.default_interval // 2
        self.interval = self.default_interval
        self.init_block_time = 0
        self.total = len(nodes)
        self.my_id = conf["id"] % self.total
        self.logger = logging.getLogger(self.__class__.__name__)

        self.messenger = MessengerFactory.get_messenger(conf["msgtype"], nodes, self.my_id)
        self.signer = signer
        self.nsigs = conf["nsigs"]

        self.inflation = None
        if in_rate > 0:
            self.inflation = Inflation(self.total, self.my_id, self.elementsd, self.default_interval,\
                in_rate, in_period, in_address, script, conf["reissuanceprivkey"])

    def set_init_block_time(self):
        if self.init_block_time == 0:
            block_hash = self.get_blockhash(1)
            if block_hash == None:
                return False
            block_header = self.get_blockheader(block_hash)
            if block_header == None or 'time' not in block_header:
                return False
            self.init_block_time = round_time(self.default_interval, block_header['time'])
        return True

    def is_catchup_needed(self, height):
        if height == 0:
            return False
        height_expected = (round_time(self.default_interval, int(time())) - self.init_block_time)\
                         // self.default_interval
        if height_expected > height:
            self.logger.warning("Current chain height {} expected {}".format(height, height_expected))
            return True
        else:
            self.logger.info("Current chain height: {}".format(height))

        return False

    def run(self):
        while not self.stopped():
            sleep(self.interval - time() % self.interval)
            start_time = int(time())
            step = int(time()) % (self.interval * self.total) / self.interval

            height = self.get_blockcount()
            if height == None:
                continue
            elif height > 0 and not self.set_init_block_time():
                self.logger.error("Could not set init block time")
                continue

            if self.is_catchup_needed(height):
                if self.inflation is not None and self.inflation.is_inflation_step(height):
                    self.logger.info("Catch up mode skipped due to inflation step")
                else:
                    self.interval = self.catchup_interval
                    self.logger.info("Catch up mode enabled")
            else:
                self.interval = self.default_interval

            if self.my_id != int(step):
                # NOT OUR TURN - GET BLOCK AND SEND SIGNATURE ONLY
                self.logger.info("Node {} - consumer".format(self.my_id))

                new_block = None
                while new_block == None:
                    if (time() - start_time) >= (self.interval / 3): # time limit to get block
                        break
                    new_block = self.messenger.consume_block(height)

                if new_block == None:
                    self.logger.warning("Failed to receive expected block proposal")
                    self.messenger.reconnect()
                    continue
                else:
                    self.logger.info("Received block proposal: %s", new_block)

                sig = {}
                sig["blocksig"] = self.get_blocksig(new_block["blockhex"])
                if sig["blocksig"] == None:
                    self.logger.error("Failed to sign block proposal")
                    self.stop()
                    continue
                else:
                    self.logger.info("Signed block proposal: %s", sig["blocksig"])

                # Inflation only, check to see if there are any reissuance transactions to sign
                if height > 0 and self.inflation is not None:
                    txsigs = self.inflation.get_tx_sigs(self.elementsd, height, new_block)
                    if txsigs is not None:
                        sig["txsigs"] = txsigs
                        sig["id"] = self.my_id

                self.messenger.produce_sig(sig, height + 1)
                self.logger.info("Sent block sig: %s", sig)
                elapsed_time = time() - start_time
                sleep(self.interval / 2 - (elapsed_time if elapsed_time < self.interval / 2 else 0))
            else:
                # OUR TURN - FIRST SEND NEW BLOCK HEX
                self.logger.info("Node {} - producer".format(self.my_id))

                block = {}
                block["blockhex"] = self.get_newblockhex()
                if block["blockhex"] == None:
                    self.logger.error("Failed to generate block proposal")
                    continue
                else:
                    self.logger.info("Generated block proposal: %s", block["blockhex"])

                #if reissuance step, create raw reissuance transactions
                if height > 0 and self.inflation is not None:
                    try:
                        txs = self.inflation.create_txs(self.elementsd, height)
                        if txs is not None:
                            block["txs"] = txs
                    except Exception as e:
                        self.logger.error(e)
                        self.stop()
                        continue

                self.messenger.produce_block(block, height + 1)
                self.logger.info("Sent block proposal: %s", block)
                elapsed_time = time() - start_time
                sleep(self.interval / 2 - (elapsed_time if elapsed_time < self.interval / 2 else 0))

                # THEN COLLECT SIGNATURES AND SUBMIT BLOCK
                sigs = self.messenger.consume_sigs(height)
                self.logger.info("Received %s sigs", len(sigs))
                if len(sigs) < self.nsigs - 1:
                    self.logger.warning("Failed to receive at least %s sigs", self.nsigs - 1)
                    self.messenger.reconnect()
                    continue
                else:
                    for sig in sigs:
                        self.logger.info("Received block sig: %s", sig)

                if self.inflation is not None and "txs" in block and block["txs"] is not None:
                    if not self.inflation.send_txs(self.elementsd, height, block, sigs):
                        continue

                blocksigs = []
                for sig in sigs:
                    blocksigs = blocksigs + sig["blocksig"]
                self.generate_signed_block(block["blockhex"], blocksigs)

    def rpc_retry(self, rpc_func, *args):
        # The following commented block is work in progress to remove the need to self.stop() after a limited number of retrys
        #while True:
        #    try:
        #        return rpc_func(*args)
        #    except Exception as e:
        #        self.logger.warning("Retrying RPC call, following elementsd error: {}".format(e))
        #        self.elementsd = getelementsd(self.conf)
        #        sleep(10) # Pause for 10 seconds between retries, so as not to cause a flood
        for i in range(5):
            try:
                return rpc_func(*args)
            except Exception as e:
                self.logger.warning("{}\nReconnecting to elementsd rpc server...".format(e))
                self.elementsd = getelementsd(self.conf)
        self.logger.error("Failed reconnecting to elementsd rpc server")
        self.stop()

    def get_IBDstatus(self):
        json_dict = self.rpc_retry(self.elementsd.getblockchaininfo)
        return json_dict['initialblockdownload']

    def get_blockcount(self):
        return self.rpc_retry(self.elementsd.getblockcount)

    def get_newblockhex(self):
        while self.get_IBDstatus():
            self.logger.warning("elementsd in IBD mode, retrying...")
            sleep(1)
        return self.rpc_retry(self.elementsd.getnewblockhex)

    def get_blockhash(self, height):
        return self.rpc_retry(self.elementsd.getblockhash, height)

    def get_blockheader(self, hash):
        return self.rpc_retry(self.elementsd.getblockheader, hash)

    def get_blocksig(self, block):
        try:
            # hsm block signer
            if self.signer is not None:
                # get block header bytes excluding last byte (Elements SER_HASH BlockHeader)
                block_header_bytes = get_header(bytes.fromhex(block))
                block_header_for_hash_bytes = block_header_bytes[:len(block_header_bytes)-1]

                # sign the hashed (once not twice) block header bytes
                sig = self.signer.sign(sha256(block_header_for_hash_bytes))

                # turn sig into scriptsig format
                return "00{:02x}{}".format(len(sig), sig.hex())

            while self.get_IBDstatus():
                self.logger.warning("elementsd in IBD mode, retrying...")
                sleep(1)
            self.rpc_retry(self.elementsd.walletpassphrase, self.wallet_pass_phrase, 2)
            return self.rpc_retry(self.elementsd.signblock, block, self.default_redeem_script)
        except Exception as e:
            self.logger.warning("{}\nFailed to sign block proposal".format(e))
            return None

    def generate_signed_block(self, block, sigs):
        try:
            sig = self.get_blocksig(block)
            sigs = sigs + sig
            self.logger.info("Signed block proposal: %s", sig)
            blockresult = self.rpc_retry(self.elementsd.combineblocksigs, block, sigs, self.default_redeem_script)
            signedblock = blockresult["hex"]
            if blockresult["complete"] == True:
                self.rpc_retry(self.elementsd.submitblock, signedblock)
                self.logger.info("Node {} - submitted block {}".format(self.my_id, signedblock))
            else:
                self.logger.info("Node {} - failed to submit block".format(self.my_id))
        except Exception as e:
            self.logger.warning("{}\nFailed to generate signed block".format(e))

ELEMENTS_BASE_HEADER_SIZE = 172

def header_hash(block):
    challenge_size = block[ELEMENTS_BASE_HEADER_SIZE]
    header_without_proof = block[:ELEMENTS_BASE_HEADER_SIZE+1+challenge_size]
    return double_sha256(header_without_proof)

def get_header(block):
    challenge_size = block[ELEMENTS_BASE_HEADER_SIZE]
    proof_size = block[ELEMENTS_BASE_HEADER_SIZE+1+challenge_size]
    return block[:ELEMENTS_BASE_HEADER_SIZE+1+challenge_size+1+proof_size]

def sha256(x):
    return _sha256(x).digest()

def double_sha256(x):
    return sha256(sha256(x))
