import simpy
import random
import math as m

SIMULATION_TIME = 1000 # mins
ARRIVAL_RATE = 30 * 60 / SIMULATION_TIME # arrival rate of customers per 60 mins

PREORDER_CUSTOMER_PROBABILITY = 0.4

AVG_SERVICE_TIME_BAR = 4.5 # min per customer
AVG_SERVICE_TIME_NORMAL = 60 # min per customer
AVG_SERVICE_TIME_PREORDER = 40 # min per customer

SERVICE_RATE_BAR = 1.0 / AVG_SERVICE_TIME_BAR
SERVICE_RATE_NORMAL = 1.0 / AVG_SERVICE_TIME_NORMAL
SERVICE_RATE_PREORDER = 1.0 / AVG_SERVICE_TIME_PREORDER

GATE_LENGTH = 3
PRE_ORDER_QUEUE_LENGTH = 6
NORMAL_QUEUE_LENGTH = 2

NUM_BAR_TABLES = 3
NUM_NORMAL_TABLES = 3
NUM_PREORDER_TABLES = 3

# GATE_LENGTH = 10
# PRE_ORDER_QUEUE_LENGTH = 15
# NORMAL_QUEUE_LENGTH = 5

# NUM_BAR_TABLES = 25
# NUM_NORMAL_TABLES = 20
# NUM_PREORDER_TABLES = 5

NORMAL_CUSTOMER_LESS_THAN_5 = 1 - m.exp(- SERVICE_RATE_NORMAL * 5)

# Environment
env = simpy.Environment()


class Action:
    Enter = "enters"
    Leave = "leaves"
    Finish = "Finishes"
    Discard = "Discard by"


def logger(name, action, component, time):
    print(f'{name} {action} {component} at {time:.2f}')


class Customer:
    instance_count = 0

    def __init__(self,  name: str, is_preorder) -> None:
        self.name = name
        self.is_preorder = is_preorder
        self.entry_queue_wait_time = 0
        self.preorder_queue_wait_time = 0
        self.normal_queue_wait_time = 0
        self.timer = 0

    def start_wait(self):
        self.timer = env.now

    def end_wait(self):
        return env.now - self.timer

    def set_entry_queue_wait_time(self, time):
        self.entry_queue_wait_time = time

    def set_preorder_queue_wait_time(self, time):
        self.preorder_queue_wait_time = time

    def set_normal_queue_wait_time(self, time):
        self.set_normal_queue_wait_time = time

    def __str__(self) -> str:
        return self.name + '_' + str(self.is_preorder)

    @classmethod
    def create_random_customer(cls):
        customer = cls(f'customer_{cls.instance_count}', get_random_preorder())
        cls.instance_count += 1
        return customer


class Queue:
    def __init__(self, capacity, name) -> None:
        self._capacity = capacity
        self.customers: list[Customer] = []
        self.name = name

    def __str__(self) -> str:
        return self.name

    # mutator
    def push(self, customer: Customer):
        if self.is_full:
            return False
        self.customers.append(customer)
        return True

    def get_first(self):
        if self.is_full:
            return None
        return self.customers[0]

    def pop(self) -> Customer or None:
        if not self.is_empty:
            customer = self.customers.pop(0)
            return customer
        return None

    # Properties
    @property
    def length(self):
        return len(self.customers)

    @property
    def is_full(self):
        return self.length == self._capacity

    @property
    def is_empty(self):
        return self.length == 0

    # Factories
    @classmethod
    def create_entry_queue(cls):
        return cls(GATE_LENGTH, 'EntryQueue')

    @classmethod
    def create_preorder_queue(cls):
        return cls(PRE_ORDER_QUEUE_LENGTH, 'PreOrderQueue')

    @classmethod
    def create_food_serve_queue(cls):
        return cls(NORMAL_QUEUE_LENGTH, 'NormalQueue')


class Server(simpy.Resource):
    def __init__(self, env, capacity, name) -> None:
        super(Server, self).__init__(env, capacity)
        self.name = name

    def __str__(self) -> str:
        return self.name

    # Factories
    @classmethod
    def create_bar_area_server(cls):
        return cls(env, NUM_BAR_TABLES, 'BarArea')

    @classmethod
    def create_preorder_server(cls):
        return cls(env, NUM_PREORDER_TABLES, 'PreOrderTables')

    @classmethod
    def create_normal_server(cls):
        return cls(env, NUM_NORMAL_TABLES, 'NormalTables')


class Simulator:
    def __init__(self) -> None:
        self.bar_area = Server.create_bar_area_server()
        self.preorder_area = Server.create_preorder_server()
        self.normal_area = Server.create_normal_server()

        self.entry_queue = Queue.create_entry_queue()
        self.preorder_queue = Queue.create_preorder_queue()
        self.normal_queues = [
            Queue.create_food_serve_queue() for i in range(3)
        ]

        self.discarded_by_entry_queue_customers = []
        self.discarded_by_normal_queue_customer = []
        self.discarded_by_preorder_queue_customer = []
        self.compleded_customers = []

    def start_simulate(self):
        while True:
            # inter arrival time between customers
            yield env.timeout(get_inter_arrival_time())
            self.customer_arrive()

    def customer_arrive(self):
        customer = Customer.create_random_customer()
        if not self.entry_queue.push(customer):
            # Queue fulled
            # Store discarded customer
            print("currect queue: ", self.entry_queue.length)
            logger(customer, Action.Discard, self.entry_queue, env.now)
            self.discarded_by_entry_queue_customers.append(customer)
            return

        logger(customer, Action.Enter, self.entry_queue, env.now)
        # Customer start wait in entry queue
        customer.start_wait()
        self.delivery_customer()

    def delivery_customer(self):
        customer = self.entry_queue.get_first()
        if customer:
            if customer.is_preorder:
                # Customer is preorder => Wait until preorder server is free
                env.process(self.serve_preorder_area_from_entry_queue())
            else:
                # Customer is served at bar area
                env.process(self.serve_bar_area_customer())
        # No customer

    def serve_bar_area_customer(self):
        with self.bar_area.request() as request:
            yield request
            customer = self.entry_queue.pop()
            logger(customer, Action.Leave, self.entry_queue, env.now)

            entry_wait_time = customer.end_wait()
            customer.entry_queue_wait_time = entry_wait_time

            # Serve customer in bar area
            service_time = get_random_service_time(SERVICE_RATE_BAR)
            logger(customer, Action.Enter, self.bar_area, env.now)
            yield env.timeout(service_time)
            logger(customer, Action.Leave, self.bar_area, env.now)

            if service_time <= 5.0:
                # Customer with service time < 5 go to queue
                logger(customer, Action.Enter, self.preorder_queue, env.now)
                self.preorder_queue.push(customer)
                customer.start_wait()
                env.process(self.serve_preorder_area_from_bar_area())
            else:
                available_queue = None
                for q in self.normal_queues:
                    if not q.is_full:
                        available_queue = q
                if not available_queue:
                    logger(customer, Action.Discard, available_queue, env.now)
                    # Cusomter discarded
                    return
                logger(customer, Action.Enter, available_queue, env.now)
                available_queue.push(customer)
                env.process(self.serve_normal_area(available_queue))

    # DONE
    def serve_normal_area(self, queue: Queue):
        with self.normal_area.request() as request:
            yield request
            customer = queue.pop()
            customer.normal_queue_wait_time = customer.end_wait()
            logger(customer, Action.Leave, queue, env.now)
            logger(customer, Action.Enter, self.normal_area, env.now)
            yield env.timeout(get_random_service_time(SERVICE_RATE_NORMAL))

    # Done
    def serve_preorder_area_from_bar_area(self):
        with self.preorder_area.request() as request:
            yield request
            customer = self.preorder_queue.pop()
            logger(customer, Action.Leave, self.preorder_queue, env.now)
            customer.preorder_queue_wait_time = customer.end_wait()
            logger(customer, Action.Enter, self.preorder_area, env.now)
            yield env.timeout(get_random_service_time(SERVICE_RATE_PREORDER))
            logger(customer, Action.Leave, self.preorder_area, env.now)

    # DONE
    def serve_preorder_area_from_entry_queue(self):
        with self.preorder_area.request() as request:
            yield request
            customer = self.entry_queue.pop()
            logger(customer, Action.Leave, self.entry_queue, env.now)
            customer.entry_queue_wait_time = customer.end_wait()
            logger(customer, Action.Enter, self.preorder_area, env.now)
            yield env.timeout(get_random_service_time(SERVICE_RATE_PREORDER))
            logger(customer, Action.Finish, self.preorder_area, env.now)
            # Store completed customers


def get_inter_arrival_time():
    time = random.expovariate(ARRIVAL_RATE)
    return time


def get_random_preorder():
    return random.random() <= PREORDER_CUSTOMER_PROBABILITY


def get_random_service_time(rate):
    time = random.expovariate(rate)
    print('service time: %.2f' % time)
    return time


s = Simulator()
env.process(s.start_simulate())
env.run(until=SIMULATION_TIME)
