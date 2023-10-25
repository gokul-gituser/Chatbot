from fastapi import FastAPI
from fastapi import Request
from fastapi.responses import JSONResponse
import db
import helper

app = FastAPI()

orders_in_progress = {}


@app.post("/")
async def handle_request(request: Request):
    payload = await request.json()


    intent = payload['queryResult']['intent']['displayName']
    parameters = payload['queryResult']['parameters']
    output_contexts = payload['queryResult']['outputContexts']

    session_id = helper.extract_session_id(output_contexts[0]["name"])

    intent_handler_dict = {
        'order.add - context: ongoing-order': add_to_order,
        'order.remove - context: ongoing-order': remove_from_order,
        'order.complete - context: ongoing-order': complete_order,
        'track.order - context: ongoing-tracking': track_order
    }

    return intent_handler_dict[intent](parameters, session_id)


def add_to_order(parameters: dict, session_id: str):
    food_items = parameters["food-item"]
    quantity = parameters["number"]

    if len(food_items) != len(quantity):
        fulfillment_text = "Sorry I didn't understand. Can you please specify food items and quantities clearly?"
    else:
        new_order_dict = dict(zip(food_items, quantity))

        if session_id in orders_in_progress:
            current_order_dict = orders_in_progress[session_id]
            current_order_dict.update(new_order_dict)
            orders_in_progress[session_id] = current_order_dict

        else:
            orders_in_progress[session_id] = new_order_dict

        orders_in_progress_str = helper.get_str_from_food_dict(orders_in_progress[session_id])
        fulfillment_text = f"You have ordered {orders_in_progress_str} so far. Do you need anything else?"

    return JSONResponse(content={
        "fulfillmentText": fulfillment_text
    })


def complete_order(parameters: dict, session_id: str):
    if session_id not in orders_in_progress:
        fulfillment_text = " Sorry! I'm having trouble finding your order. Can you place a new order?"
    else:
        final_order = orders_in_progress[session_id]
        order_id = save_to_db(final_order)
        if order_id == -1:
            fulfillment_text = "Sorry, I couldn't process your order due to a backend error. " \
                               "Please place a new order"
        else:
            order_total = db.get_total_order_price(order_id)

            fulfillment_text = f"We have placed your order. " \
                               f"your order id is {order_id}. " \
                               f"Your order total is {order_total}. You can pay at the time of delivery!"

        del orders_in_progress[session_id]

    return JSONResponse(content={
        "fulfillmentText": fulfillment_text
    })


def save_to_db(final_order: dict):
    next_order_id = db.get_next_order_id()

    
    for food_item, quantity in final_order.items():
        rcode = db.insert_order_item(
            food_item,
            quantity,
            next_order_id
        )

        if rcode == -1:
            return -1

    
    db.insert_order_tracking(next_order_id, "in progress")

    return next_order_id


def remove_from_order(parameters: dict, session_id: str):
    if session_id not in orders_in_progress:
        return JSONResponse(content={
            "fulfillmentText": "Sorry!I'm having a trouble finding your order. Please place a new order"
        })

    current_order = orders_in_progress[session_id]
    food_items = parameters["food-item"]

    removed_items = []
    no_such_items = []

    for item in food_items:
        if item not in current_order:
            no_such_items.append(item)
        else:
            removed_items.append(item)
            del current_order[item]

    if len(removed_items) > 0:
        fulfillment_text = f'Removed {",".join(removed_items)} from your order!'

    if len(no_such_items) > 0:
        fulfillment_text = f' Your current order does not have {",".join(no_such_items)}'

    if len(current_order.keys()) == 0:
        fulfillment_text += " Your order is empty!"
    else:
        order_str = helper.get_str_from_food_dict(current_order)
        fulfillment_text += f"Now you have {order_str} in your order"

    return JSONResponse(content={
        "fulfillmentText": fulfillment_text
    })


def track_order(parameters: dict, session_id: str):
    order_id = int(parameters['order_id'])
    order_status = db.get_order_status(order_id)

    if order_status:
        fulfillment_text = f"Your order with id {order_id} is {order_status}"
    else:
        fulfillment_text = f"no order for id {order_id}"

    return JSONResponse(content={
        "fulfillmentText": fulfillment_text
    })
