from typing import Dict, List, Tuple, Optional, Set
from datetime import datetime
import uuid
from decimal import Decimal
from enum import Enum
import json


class SplitType(Enum):
    EQUAL = "equal"
    PERCENTAGE = "percentage"
    EXACT = "exact"


class User:
    
    def __init__(self, user_id: str, name: str, email: str):
        self.user_id = user_id
        self.name = name
        self.email = email
        
    def to_dict(self) -> Dict:
        return {
            "user_id": self.user_id,
            "name": self.name,
            "email": self.email
        }
    
    @classmethod
    def from_dict(cls, data: Dict) -> 'User':



        return cls(
            user_id=data["user_id"],
            name=data["name"],
            email=data["email"]
        )


class Transaction:

    def __init__(self, 
                 transaction_id: str,
                 description: str,
                 date: datetime,
                 payers: Dict[str, Decimal],  # Dictionary mapping user_id to amount paid
                 participants: List[str],     # List of user_ids participating in the expense
                 split_type: SplitType = SplitType.EQUAL,
                 split_details: Optional[Dict[str, Decimal]] = None):  # For non-equal splits
        
        self.transaction_id = transaction_id
        self.description = description
        self.date = date
        self.payers = payers
        self.participants = participants
        self.split_type = split_type
        self.split_details = split_details or {}
        
        # Calculate total amount of transaction
        self.total_amount = sum(payers.values())
        
        # Validate the transaction
        self._validate()
        
    def _validate(self):
        # Ensure all payers are valid (have positive payment amounts)
        for user_id, amount in self.payers.items():
            if amount <= 0:
                raise ValueError(f"Payment amount must be positive for user {user_id}")
                
        # For percentage split, ensure percentages sum to 100
        if self.split_type == SplitType.PERCENTAGE and self.split_details:
            total_percentage = sum(self.split_details.values())
            if abs(total_percentage - Decimal('100')) > Decimal('0.01'):
                raise ValueError(f"Percentage split must sum to 100%, got {total_percentage}%")
                
        # For exact split, ensure amounts sum to total
        if self.split_type == SplitType.EXACT and self.split_details:
            total_split = sum(self.split_details.values())
            if abs(total_split - self.total_amount) > Decimal('0.01'):
                raise ValueError(f"Exact split amounts must sum to {self.total_amount}, got {total_split}")
    
    def get_user_share(self, user_id: str) -> Decimal:

        if user_id not in self.participants:
            return Decimal('0')
            
        if self.split_type == SplitType.EQUAL:
            return self.total_amount / len(self.participants)
        elif self.split_type == SplitType.PERCENTAGE:
            if user_id not in self.split_details:
                return Decimal('0')
            return (self.split_details[user_id] / Decimal('100')) * self.total_amount
        elif self.split_type == SplitType.EXACT:
            if user_id not in self.split_details:
                return Decimal('0')
            return self.split_details[user_id]
        
        return Decimal('0')
    
    def get_user_payment(self, user_id: str) -> Decimal:

        return self.payers.get(user_id, Decimal('0'))
    
    def get_user_balance(self, user_id: str) -> Decimal:

        paid = self.get_user_payment(user_id)
        owed = self.get_user_share(user_id)
        return paid - owed
    
    def to_dict(self) -> Dict:

        return {
            "transaction_id": self.transaction_id,
            "description": self.description,
            "date": self.date.isoformat(),
            "payers": {k: str(v) for k, v in self.payers.items()},
            "participants": self.participants,
            "split_type": self.split_type.value,
            "split_details": {k: str(v) for k, v in self.split_details.items()} if self.split_details else {},
            "total_amount": str(self.total_amount)
        }
    
    @classmethod
    def from_dict(cls, data: Dict) -> 'Transaction':

        return cls(
            transaction_id=data["transaction_id"],
            description=data["description"],
            date=datetime.fromisoformat(data["date"]),
            payers={k: Decimal(v) for k, v in data["payers"].items()},
            participants=data["participants"],
            split_type=SplitType(data["split_type"]),
            split_details={k: Decimal(v) for k, v in data["split_details"].items()} if data["split_details"] else None
        )


class ExpenseManager:

    
    def __init__(self):
        # Dictionary to store user objects with user_id as key
        self.users: Dict[str, User] = {}
        
        # Dictionary to store transaction objects with transaction_id as key
        self.transactions: Dict[str, Transaction] = {}
        
        # Dictionary to store user transactions for quick lookup
        # Maps user_id to a set of transaction_ids involving that user
        self.user_transactions: Dict[str, Set[str]] = {}
        
        # Cache for user balances - will be invalidated when transactions change
        self._balance_cache: Dict[str, Dict[str, Decimal]] = {}
        self._cache_valid = False
    
    def add_user(self, name: str, email: str) -> User:
        user_id = str(uuid.uuid4())
        user = User(user_id, name, email)
        self.users[user_id] = user
        self.user_transactions[user_id] = set()
        
        # Invalidate balance cache when users change
        self._cache_valid = False
        
        return user
    
    def get_user(self, user_id: str) -> Optional[User]:

        return self.users.get(user_id)
    
    def get_all_users(self) -> List[User]:
        return list(self.users.values())
    
    def add_transaction(self, 
                       description: str,
                       payers: Dict[str, Decimal],
                       participants: List[str],
                       split_type: SplitType = SplitType.EQUAL,
                       split_details: Optional[Dict[str, Decimal]] = None) -> Transaction:

        # Validate that all users exist
        for user_id in list(payers.keys()) + participants:
            if user_id not in self.users:
                raise ValueError(f"User {user_id} does not exist")
        
        transaction_id = str(uuid.uuid4())
        transaction = Transaction(
            transaction_id=transaction_id,
            description=description,
            date=datetime.now(),
            payers=payers,
            participants=participants,
            split_type=split_type,
            split_details=split_details
        )
        
        self.transactions[transaction_id] = transaction
        
        # Update user_transactions index
        for user_id in set(payers.keys()).union(set(participants)):
            if user_id in self.user_transactions:
                self.user_transactions[user_id].add(transaction_id)
            else:
                self.user_transactions[user_id] = {transaction_id}
        
        # Invalidate balance cache
        self._cache_valid = False
                
        return transaction
    
    def get_transaction(self, transaction_id: str) -> Optional[Transaction]:
        return self.transactions.get(transaction_id)
    
    def get_user_transactions(self, user_id: str) -> List[Transaction]:

        if user_id not in self.user_transactions:
            return []
            
        transaction_ids = self.user_transactions[user_id]
        return [self.transactions[tid] for tid in transaction_ids if tid in self.transactions]
    
    def _calculate_balances(self) -> Dict[str, Dict[str, Decimal]]:

        # Initialize balances matrix
        balances = {user_id: {other_id: Decimal('0') for other_id in self.users if other_id != user_id} 
                   for user_id in self.users}
        
        # Process all transactions
        for transaction in self.transactions.values():
            for user_id in self.users:
                user_balance = transaction.get_user_balance(user_id)
                if user_balance != 0:
                    # This user has a non-zero balance in this transaction
                    # If positive, they are owed money; if negative, they owe money
                    for other_id in self.users:
                        if other_id != user_id:
                            other_balance = transaction.get_user_balance(other_id)
                            if other_balance < 0 and user_balance > 0:
                                # Other user owes money, and this user is owed money
                                # Calculate how much of other's debt should be paid to this user
                                total_positive = sum(
                                    max(transaction.get_user_balance(uid), 0) 
                                    for uid in transaction.participants 
                                    if uid != other_id
                                )
                                if total_positive > 0:
                                    # This user's share of the other's debt
                                    share = (user_balance / total_positive) * abs(other_balance)
                                    balances[other_id][user_id] += share
        
        return balances
    
    def get_balances(self) -> Dict[str, Dict[str, Decimal]]:
        if not self._cache_valid:
            self._balance_cache = self._calculate_balances()
            self._cache_valid = True
            
        return self._balance_cache
    
    def get_user_balance(self, user_id: str) -> Dict[str, Decimal]:

        if user_id not in self.users:
            raise ValueError(f"User {user_id} does not exist")
            
        balances = self.get_balances()
        
        # Calculate what this user owes to others
        owes = {other_id: amount for other_id, amount in balances[user_id].items() if amount > 0}
        
        # Calculate what others owe to this user
        owed = {other_id: amount for other_id, amount in 
                {o_id: balances[o_id].get(user_id, Decimal('0')) for o_id in self.users if o_id != user_id}.items() 
                if amount > 0}
        
        # Calculate net balance
        net = {}
        for other_id in self.users:
            if other_id != user_id:
                owed_amount = owed.get(other_id, Decimal('0'))
                owes_amount = owes.get(other_id, Decimal('0'))
                if owed_amount > owes_amount:
                    net[other_id] = owed_amount - owes_amount  # Positive: other owes user
                elif owes_amount > owed_amount:
                    net[other_id] = -(owes_amount - owed_amount)  # Negative: user owes other
        
        return net
    
    def get_simplified_settlements(self) -> List[Tuple[str, str, Decimal]]:

        # Create a list of all net balances
        balances = []
        for user_id in self.users:
            net_balance = sum(
                transaction.get_user_balance(user_id) 
                for transaction in self.transactions.values()
                if user_id in transaction.participants or user_id in transaction.payers
            )
            balances.append((user_id, net_balance))
        
        # Sort by balance (ascending)
        balances.sort(key=lambda x: x[1])
        
        settlements = []
        
        # While there are unprocessed balances
        i, j = 0, len(balances) - 1
        while i < j:
            # Get users with most negative and most positive balances
            debtor, debt = balances[i]
            creditor, credit = balances[j]
            
            if abs(debt) < Decimal('0.01') and abs(credit) < Decimal('0.01'):
                # Both balances are effectively zero
                i += 1
                j -= 1
                continue
                
            if debt >= 0 or credit <= 0:
                # No more meaningful settlements to make
                break
                
            # Calculate settlement amount
            amount = min(abs(debt), credit)
            if amount > Decimal('0.01'):  # Only create settlement if amount is significant
                settlements.append((debtor, creditor, amount))
            
            # Update balances
            balances[i] = (debtor, debt + amount)
            balances[j] = (creditor, credit - amount)
            
            # Move pointers if balances are settled
            if abs(balances[i][1]) < Decimal('0.01'):
                i += 1
            if abs(balances[j][1]) < Decimal('0.01'):
                j -= 1
        
        return settlements
    
    def save_to_file(self, filename: str):
   
        data = {
            "users": {uid: user.to_dict() for uid, user in self.users.items()},
            "transactions": {tid: transaction.to_dict() for tid, transaction in self.transactions.items()},
            "user_transactions": {uid: list(tids) for uid, tids in self.user_transactions.items()}
        }
        
        with open(filename, 'w') as f:
            json.dump(data, f, indent=2)
    
    @classmethod
    def load_from_file(cls, filename: str) -> 'ExpenseManager':

        with open(filename, 'r') as f:
            data = json.load(f)
        
        manager = cls()
        
        # Load users
        for uid, user_data in data["users"].items():
            user = User.from_dict(user_data)
            manager.users[uid] = user
        
        # Load transactions
        for tid, transaction_data in data["transactions"].items():
            transaction = Transaction.from_dict(transaction_data)
            manager.transactions[tid] = transaction
        
        # Load user_transactions
        for uid, tids in data["user_transactions"].items():
            manager.user_transactions[uid] = set(tids)
        
        return manager


class ExpenseCLI:

    
    def __init__(self):
        self.expense_manager = ExpenseManager()
        self.commands = {
            "help": self.help,
            "add_user": self.add_user,
            "list_users": self.list_users,
            "get_user": self.get_user,
            "add_transaction": self.add_transaction,
            "get_transaction": self.get_transaction,
            "get_user_transactions": self.get_user_transactions,
            "get_user_balance": self.get_user_balance,
            "get_settlements": self.get_settlements,
            "save": self.save,
            "load": self.load,
            "exit": self.exit
        }
    
    def help(self):
        
        print("Available commands:")
        for cmd in self.commands:
            print(f"- {cmd}")
    
    def add_user(self):
  
        name = input("Enter user name: ")
        email = input("Enter user email: ")
        
        try:
            user = self.expense_manager.add_user(name, email)
            print(f"User added with ID: {user.user_id}")
        except Exception as e:
            print(f"Error adding user: {str(e)}")
    
    def list_users(self):
       
        users = self.expense_manager.get_all_users()
        if not users:
            print("No users found.")
            return
            
        print("Users:")
        for user in users:
            print(f"ID: {user.user_id}, Name: {user.name}, Email: {user.email}")
    
    def get_user(self):
    
        user_id = input("Enter user ID: ")
        user = self.expense_manager.get_user(user_id)
        
        if user:
            print(f"ID: {user.user_id}, Name: {user.name}, Email: {user.email}")
        else:
            print(f"User with ID {user_id} not found.")
    
    def add_transaction(self):
     
        description = input("Enter transaction description: ")
        
        # Get payers
        payers = {}
        payer_count = int(input("Enter number of payers: "))
        for i in range(payer_count):
            payer_id = input(f"Enter payer {i+1} ID: ")
            amount = input(f"Enter amount paid by {payer_id}: ")
            payers[payer_id] = Decimal(amount)
        
        # Get participants
        participants = []
        participant_count = int(input("Enter number of participants: "))
        for i in range(participant_count):
            participant_id = input(f"Enter participant {i+1} ID: ")
            participants.append(participant_id)
        
        # Get split type
        print("Split types: equal, percentage, exact")
        split_type_str = input("Enter split type (default: equal): ") or "equal"
        try:
            split_type = SplitType(split_type_str)
        except ValueError:
            print(f"Invalid split type {split_type_str}, using EQUAL instead.")
            split_type = SplitType.EQUAL
        
        # Get split details if needed
        split_details = None
        if split_type != SplitType.EQUAL:
            split_details = {}
            for participant_id in participants:
                if split_type == SplitType.PERCENTAGE:
                    value = input(f"Enter percentage for {participant_id}: ")
                else:  # EXACT
                    value = input(f"Enter exact amount for {participant_id}: ")
                split_details[participant_id] = Decimal(value)
        
        try:
            transaction = self.expense_manager.add_transaction(
                description=description,
                payers=payers,
                participants=participants,
                split_type=split_type,
                split_details=split_details
            )
            print(f"Transaction added with ID: {transaction.transaction_id}")
        except Exception as e:
            print(f"Error adding transaction: {str(e)}")
    
    def get_transaction(self):

        transaction_id = input("Enter transaction ID: ")
        transaction = self.expense_manager.get_transaction(transaction_id)
        
        if transaction:
            print(f"ID: {transaction.transaction_id}")
            print(f"Description: {transaction.description}")
            print(f"Date: {transaction.date}")
            print(f"Total amount: {transaction.total_amount}")
            print(f"Split type: {transaction.split_type.value}")
            
            print("Payers:")
            for user_id, amount in transaction.payers.items():
                print(f"  {user_id}: {amount}")
            
            print("Participants:")
            for user_id in transaction.participants:
                share = transaction.get_user_share(user_id)
                print(f"  {user_id}: owes {share}")
        else:
            print(f"Transaction with ID {transaction_id} not found.")
    
    def get_user_transactions(self):

        user_id = input("Enter user ID: ")
        transactions = self.expense_manager.get_user_transactions(user_id)
        
        if not transactions:
            print(f"No transactions found for user {user_id}.")
            return
            
        print(f"Transactions for user {user_id}:")
        for transaction in transactions:
            balance = transaction.get_user_balance(user_id)
            status = "owes" if balance < 0 else "is owed"
            print(f"ID: {transaction.transaction_id}, Description: {transaction.description}, " 
                  f"Date: {transaction.date}, {status} {abs(balance)}")
    
    def get_user_balance(self):

        user_id = input("Enter user ID: ")
        try:
            balances = self.expense_manager.get_user_balance(user_id)
            
            if not balances:
                print(f"User {user_id} has no outstanding balances.")
                return
                
            print(f"Balances for user {user_id}:")
            for other_id, amount in balances.items():
                if amount > 0:
                    print(f"  {other_id} owes {user_id}: {amount}")
                else:
                    print(f"  {user_id} owes {other_id}: {abs(amount)}")
        except Exception as e:
            print(f"Error getting balance: {str(e)}")
    
    def get_settlements(self):

        settlements = self.expense_manager.get_simplified_settlements()
        
        if not settlements:
            print("No settlements needed.")
            return
            
        print("Simplified settlements:")
        for from_id, to_id, amount in settlements:
            from_user = self.expense_manager.get_user(from_id)
            to_user = self.expense_manager.get_user(to_id)
            print(f"  {from_user.name} ({from_id}) pays {to_user.name} ({to_id}): {amount}")
    
    def save(self):

        filename = input("Enter filename: ")
        try:
            self.expense_manager.save_to_file(filename)
            print(f"Data saved to {filename}")
        except Exception as e:
            print(f"Error saving data: {str(e)}")
    
    def load(self):

        filename = input("Enter filename: ")
        try:
            self.expense_manager = ExpenseManager.load_from_file(filename)
            print(f"Data loaded from {filename}")
        except Exception as e:
            print(f"Error loading data: {str(e)}")
    
    def exit(self):
    
        print("Exiting application.")
        return True
    
    def run(self):

        print("Expense Tracking Application")
        print("Type 'help' to see available commands")
        
        while True:
            try:
                command = input("\nEnter command: ").strip().lower()
                
                if command in self.commands:
                    if self.commands[command]():
                        break
                else:
                    print(f"Unknown command: {command}")
                    print("Type 'help' to see available commands")
            except Exception as e:
                print(f"Error: {str(e)}")


if __name__ == "__main__":
    cli = ExpenseCLI()
    cli.run()