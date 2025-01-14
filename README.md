# Elements Federation

The client used by the federation nodes of an Elements network performing block generation and signing, token inflation, and other functions.

## Instructions
1. `pip3 install -r requirements.txt`
2. `python3 setup.py build && python3 setup.py install`
3. `./run_federation` or `python3 -m federation` and provide the following arguments:
`--rpcconnect $HOST --rpcport $PORT --rpcuser $USER --rpcpass $PASS --walletpassphrase $PASSPHRASE --nnodes $NNODES --nsigs $NSIGS --blocktime $BLOCKTIME --redeemscript $REDEEMSCRIPT --id $NODE_ID --msgtype $MSG_TYPE --nodes $NODES_LIST`

Federation arguments:

- `--rpcconnect`: rpc host of Elements node
- `--rpcport`: rpc port of Elements node
- `--rpcuser`: rpc username
- `--rpcpassword`: rpc password
- `--id`: federation node id
- `--walletpassphrase`: Wallet pass phrase, used if the node's wallet is encrypted
- `--nnodes`: The number of block signing members of the federation, the n parameter in an m-of-n block signing script
- `--nsigs`: The number of signatures required for a valid block, the m parameter in an m-of-n block signing script
- `--blocktime`: Target time between blocks, in seconds (default: 60)
- `--redeemscript`: Block signing script
- `--msg_type`: Messenger type used. Possible values: 'kafka', 'zmq' (optional, default='kafka')
- `--nodes`: List of node ip/domain names for zmq only
- `--hsm`: Flag to enable signing with HSM
- `--inflationrate`: Inflation rate
- `--inflationperiod`: Inflation period (in minutes)
- `--inflationaddress`: Address for inflation payments
- `--reissuancescript`: Reissuance token script
- `--reissuanceprivkey`: Reissuance private key

Example use:

- zmq: `python3 -m federation --rpcconnect 127.0.0.1 --rpcport 18443 --rpcuser user --rpcpass pass --walletpassphrase passphrase --nnodes 3 --nsigs 2 --blocktime 60 --redeemscript "2b4c...e97f" --id 1 --msgtype zmq --nodes “node0:1503,node1:1502”`
- kafka: `python3 -m federation --rpcconnect 127.0.0.1 --rpcport 18443 --rpcuser user --rpcpass pass --walletpassphrase passphrase --nnodes 3 --nsigs 2 --blocktime 60 --redeemscript "2b4c...e97f" --id 1` (check federation.py - defaults to 5 nodes)

### Using HSMs

#### Initialisation

Assuming hsm and pkcs11 libraries setup and all config/secrets files are in place run:

`docker build --build-arg user_pin=$USER_PIN --build-arg key_label=$KEY_LABEL -f Dockerfile.hsm.init .`

This will generate a multisig script that should be used as the `signblockarg` in the elements sidechain.

#### Running

To build the federation container with hsm signing run:

`docker build --build-arg user_pin=$USER_PIN --build-arg key_label=$KEY_LABEL -f Dockerfile.hsm .`

Inside this container federation can be initiated by:

`python3 -u -m federation --rpcconnect signing1 --rpcport 18886 --rpcuser username1 --rpcpass password1 --nnodes 3 --nsigs 2 --blocktime 60 --redeemscript "2b4c...e97f" --id 1 --msgtype zmq --nodes "federation0:6666,federation1:7777,federation2:8888" --hsm 1`

### Inflating assets

The federation nodes can be used to reissue issued assets according to a fixed inflation schedule. This is enabled by setting the `--inflationrate` argument to a non zero value. The assets are then reissued every `--inflationperiod` blocks, and to the specified address. The reissuance tokens must be paid to the P2SH address of the supplied multisig script (`--reissuancescript`). The corresponding private key for the signing node (for the reissuance script) is supplied as `--reissuanceprivkey`. If inflation is enabled, the `-rescan=1` and `-recordinflation=1` flags must be set in the signing node `elementsd.conf` file. 
