# bitcoin_transactions.py
# Utilities for working with Bitcoin transactions

import json
import logging
from typing import Dict, Any, List, Optional, Union

from bitcoin_connection import get_bitcoin_connection

logger = logging.getLogger(__name__)

def parse_kwargs(kwargs_str: str) -> Dict[str, Any]:
    """
    Parse a string of key=value pairs or a JSON string into a dictionary
    
    Args:
        kwargs_str: String containing parameters as key=value pairs or JSON object
        
    Returns:
        Dict containing the parsed parameters
    """
    if not kwargs_str:
        return {}
        
    # Try to parse as JSON first
    try:
        return json.loads(kwargs_str)
    except json.JSONDecodeError:
        # Parse as key=value pairs
        result = {}
        pairs = kwargs_str.split()
        for pair in pairs:
            if "=" in pair:
                key, value = pair.split("=", 1)
                # Try to convert numeric values
                try:
                    if "." in value:
                        value = float(value)
                    else:
                        value = int(value)
                except ValueError:
                    # Keep as string if not numeric
                    pass
                
                # Handle boolean values
                if value == "true":
                    value = True
                elif value == "false":
                    value = False
                    
                result[key] = value
        return result

def get_transaction(txid: str, verbose: bool = True, blockhash: str = None) -> Dict[str, Any]:
    """
    Get transaction data by transaction ID
    
    Args:
        txid: Transaction ID
        verbose: If True, return detailed information, otherwise return hex
        blockhash: Optional block hash containing the transaction
        
    Returns:
        Transaction data
    """
    bitcoin = get_bitcoin_connection()
    command = ["getrawtransaction", txid, "1" if verbose else "0"]
    if blockhash:
        command.append(blockhash)
        
    return bitcoin.run_command(command)


    """
    Analyze a transaction with detailed information
    
    Args:
        txid: Transaction ID
        
    Returns:
        JSON string with transaction analysis
    """
    try:
        bitcoin = get_bitcoin_connection()
        
        # Get raw transaction
        tx_data = bitcoin.run_command(["getrawtransaction", txid, "1"])
        
        if "error" in tx_data:
            return json.dumps(tx_data)
            
        # Enhanced analysis data
        analysis = {
            "transaction": tx_data,
            "summary": {
                "txid": tx_data.get("txid", ""),
                "version": tx_data.get("version", 0),
                "size": tx_data.get("size", 0),
                "vsize": tx_data.get("vsize", 0),
                "weight": tx_data.get("weight", 0),
                "locktime": tx_data.get("locktime", 0),
                "input_count": len(tx_data.get("vin", [])),
                "output_count": len(tx_data.get("vout", [])),
                "total_input_value": 0,
                "total_output_value": 0,
                "fee": 0,
                "fee_rate": 0,
                "confirmations": tx_data.get("confirmations", 0)
            },
            "inputs": [],
            "outputs": []
        }
        
        # Process outputs
        outputs = tx_data.get("vout", [])
        total_output_value = 0
        
        for output in outputs:
            value = output.get("value", 0)
            total_output_value += value
            
            output_info = {
                "n": output.get("n", 0),
                "value": value,
                "address": "unknown",
                "type": "unknown"
            }
            
            script_pub_key = output.get("scriptPubKey", {})
            if "addresses" in script_pub_key and script_pub_key["addresses"]:
                output_info["address"] = script_pub_key["addresses"][0]
            elif "address" in script_pub_key:
                output_info["address"] = script_pub_key["address"]
                
            output_info["type"] = script_pub_key.get("type", "unknown")
            
            analysis["outputs"].append(output_info)
            
        analysis["summary"]["total_output_value"] = total_output_value
        
        # Process inputs (this requires additional lookups for each input transaction)
        inputs = tx_data.get("vin", [])
        total_input_value = 0
        
        for input_data in inputs:
            input_info = {
                "sequence": input_data.get("sequence", 0),
                "txid": input_data.get("txid", ""),
                "vout": input_data.get("vout", 0),
                "value": 0,
                "address": "unknown"
            }
            
            # For regular transactions (not coinbase)
            if "txid" in input_data and "vout" in input_data:
                try:
                    input_tx = bitcoin.run_command([
                        "getrawtransaction", 
                        input_data["txid"], 
                        "1"
                    ])
                    
                    if "error" not in input_tx and "vout" in input_tx:
                        vout_data = input_tx["vout"][input_data["vout"]]
                        input_info["value"] = vout_data.get("value", 0)
                        total_input_value += input_info["value"]
                        
                        script_pub_key = vout_data.get("scriptPubKey", {})
                        if "addresses" in script_pub_key and script_pub_key["addresses"]:
                            input_info["address"] = script_pub_key["addresses"][0]
                        elif "address" in script_pub_key:
                            input_info["address"] = script_pub_key["address"]
                except Exception as e:
                    logger.error(f"Error getting input transaction: {str(e)}")
            
            analysis["inputs"].append(input_info)
            
        analysis["summary"]["total_input_value"] = total_input_value
        
        # Calculate fee
        if total_input_value > 0:
            fee = total_input_value - total_output_value
            analysis["summary"]["fee"] = fee
            
            # Calculate fee rate in sat/vB
            vsize = tx_data.get("vsize", 0)
            if vsize > 0:
                fee_rate = (fee * 100000000) / vsize  # Convert BTC to satoshis
                analysis["summary"]["fee_rate"] = fee_rate
        
        return json.dumps(analysis, indent=2)
    except Exception as e:
        logger.error(f"Error analyzing transaction: {str(e)}")
        return json.dumps({"error": str(e)})
def send_bitcoin(address: str, amount: float, comment: str = "", fee_rate: float = None) -> dict:
    """
    Send Bitcoin to an address using the bitcoin-cli.
    
    Args:
        address: The Bitcoin address to send to
        amount: Amount in BTC
        comment: Optional comment stored with transaction
        fee_rate: Optional fee rate in sat/vB
        
    Returns:
        Dictionary with transaction details
    """
    from bitcoin_connection import get_bitcoin_connection
    
    # Get connection to bitcoin-cli
    bitcoin = get_bitcoin_connection()
    
    # Prepare command arguments
    command = ["sendtoaddress", address, str(amount)]
    
    # Add comment if provided
    if comment:
        command.append(comment)
        # Add empty comment_to parameter
        command.append("")
    
    # Add fee rate if provided (fee_rate needs to be converted from sat/vB to BTC/kB)
    if fee_rate is not None:
        # Skip possible comment parameters if not provided
        if not comment:
            command.extend(["", ""])
        
        # Set subtractfeefromamount to false
        command.append("false")
        
        # Set replaceable to true for RBF
        command.append("true")
        
        # Convert sat/vB to BTC/kB for bitcoin-cli (1 sat/vB = 0.00000001 * 1000 BTC/kB)
        fee_rate_btc_kb = fee_rate * 0.00000001 * 1000
        command.append(str(fee_rate_btc_kb))
    
    # Execute the command
    result = bitcoin.execute_command(command)
    
    # Get transaction details
    tx_details = {}
    if isinstance(result, str) and len(result) == 64:  # Likely a txid
        tx_details = {
            "txid": result,
            "amount": amount,
            "address": address,
            "success": True
        }
        
        # Try to get more details about the transaction
        try:
            tx_info = get_transaction(result, True)
            if tx_info:
                tx_details["fee"] = tx_info.get("fee", 0)
                tx_details["confirmations"] = tx_info.get("confirmations", 0)
        except Exception:
            pass  # If we can't get additional details, that's okay
    else:
        tx_details = {
            "success": False,
            "result": result
        }
    
    return tx_details