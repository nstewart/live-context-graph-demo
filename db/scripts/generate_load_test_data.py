#!/usr/bin/env python3
"""
FreshMart Load Test Data Generator

Generates realistic operational data for load testing the triple store.
Creates ~700,000 triples representing 6 months of FreshMart operations.

Usage:
    python generate_load_test_data.py [--scale FACTOR] [--clear] [--dry-run]

Options:
    --scale FACTOR  Scale factor (1.0 = ~700K triples, 0.1 = ~70K triples)
    --clear         Clear existing demo data before generating
    --dry-run       Print statistics without inserting data
    --batch-size    Number of triples per INSERT batch (default: 1000)

Environment variables:
    PG_HOST, PG_PORT, PG_USER, PG_PASSWORD, PG_DATABASE
"""

import argparse
import os
import random
import sys
import uuid
from datetime import datetime, timedelta
from decimal import Decimal
from typing import List, Tuple

try:
    import psycopg2
    from psycopg2.extras import execute_values
    from faker import Faker
except ImportError:
    print("Missing dependencies. Install with:")
    print("  pip install psycopg2-binary faker")
    sys.exit(1)

# Initialize Faker with seed for reproducibility
fake = Faker()
Faker.seed(42)
random.seed(42)

# Realistic product catalog (965 hardcoded grocery items)
# Format: (name, category, price, weight_grams, perishable)
REALISTIC_PRODUCTS = [
    # DAIRY (100 products)
    ("Organic Whole Milk 1 Gallon", "Dairy", 5.99, 3785, True),
    ("Organic 2% Milk 1 Gallon", "Dairy", 5.79, 3785, True),
    ("Organic 1% Milk 1 Gallon", "Dairy", 5.69, 3785, True),
    ("Organic Skim Milk 1 Gallon", "Dairy", 5.59, 3785, True),
    ("Lactose-Free Whole Milk Half Gallon", "Dairy", 4.49, 1893, True),
    ("Lactose-Free 2% Milk Half Gallon", "Dairy", 4.29, 1893, True),
    ("Whole Milk Half Gallon", "Dairy", 3.49, 1893, True),
    ("2% Reduced Fat Milk Half Gallon", "Dairy", 3.29, 1893, True),
    ("1% Low Fat Milk Half Gallon", "Dairy", 3.19, 1893, True),
    ("Skim Milk Half Gallon", "Dairy", 3.09, 1893, True),
    ("Whole Milk Quart", "Dairy", 2.49, 946, True),
    ("Chocolate Milk Half Gallon", "Dairy", 3.99, 1893, True),
    ("Strawberry Milk Half Gallon", "Dairy", 3.99, 1893, True),
    ("Buttermilk Quart", "Dairy", 2.99, 946, True),
    ("Heavy Whipping Cream Pint", "Dairy", 4.49, 473, True),
    ("Heavy Cream Half Pint", "Dairy", 2.99, 237, True),
    ("Half and Half Pint", "Dairy", 2.49, 473, True),
    ("Half and Half Quart", "Dairy", 3.99, 946, True),
    ("Sour Cream 16oz", "Dairy", 2.99, 454, True),
    ("Sour Cream 8oz", "Dairy", 1.99, 227, True),
    ("Greek Yogurt Plain 32oz", "Dairy", 5.99, 907, True),
    ("Greek Yogurt Vanilla 32oz", "Dairy", 5.99, 907, True),
    ("Greek Yogurt Plain 5.3oz", "Dairy", 1.29, 150, True),
    ("Greek Yogurt Strawberry 5.3oz", "Dairy", 1.29, 150, True),
    ("Greek Yogurt Blueberry 5.3oz", "Dairy", 1.29, 150, True),
    ("Greek Yogurt Peach 5.3oz", "Dairy", 1.29, 150, True),
    ("Greek Yogurt Honey 5.3oz", "Dairy", 1.29, 150, True),
    ("Low-Fat Yogurt Strawberry 6oz", "Dairy", 0.99, 170, True),
    ("Low-Fat Yogurt Blueberry 6oz", "Dairy", 0.99, 170, True),
    ("Low-Fat Yogurt Peach 6oz", "Dairy", 0.99, 170, True),
    ("Low-Fat Yogurt Vanilla 6oz", "Dairy", 0.99, 170, True),
    ("Low-Fat Yogurt Cherry 6oz", "Dairy", 0.99, 170, True),
    ("Whole Milk Yogurt Plain 32oz", "Dairy", 4.99, 907, True),
    ("Skyr Icelandic Yogurt Plain 5.3oz", "Dairy", 1.79, 150, True),
    ("Skyr Icelandic Yogurt Vanilla 5.3oz", "Dairy", 1.79, 150, True),
    ("Cottage Cheese 16oz", "Dairy", 3.49, 454, True),
    ("Cottage Cheese Low-Fat 16oz", "Dairy", 3.29, 454, True),
    ("Ricotta Cheese 15oz", "Dairy", 4.49, 425, True),
    ("Cream Cheese 8oz", "Dairy", 2.99, 227, True),
    ("Cream Cheese Whipped 8oz", "Dairy", 3.29, 227, True),
    ("Neufchatel Cheese 8oz", "Dairy", 2.79, 227, True),
    ("Sharp Cheddar Cheese Block 8oz", "Dairy", 4.99, 227, True),
    ("Mild Cheddar Cheese Block 8oz", "Dairy", 4.79, 227, True),
    ("Extra Sharp Cheddar Block 8oz", "Dairy", 5.49, 227, True),
    ("Monterey Jack Cheese Block 8oz", "Dairy", 4.99, 227, True),
    ("Pepper Jack Cheese Block 8oz", "Dairy", 5.29, 227, True),
    ("Colby Jack Cheese Block 8oz", "Dairy", 4.99, 227, True),
    ("Swiss Cheese Block 8oz", "Dairy", 5.99, 227, True),
    ("Provolone Cheese Block 8oz", "Dairy", 5.49, 227, True),
    ("Mozzarella Cheese Block 8oz", "Dairy", 4.49, 227, True),
    ("Fresh Mozzarella Ball 8oz", "Dairy", 4.99, 227, True),
    ("Shredded Mozzarella 8oz", "Dairy", 3.99, 227, True),
    ("Shredded Cheddar 8oz", "Dairy", 3.99, 227, True),
    ("Shredded Mexican Blend 8oz", "Dairy", 3.99, 227, True),
    ("Shredded Italian Blend 8oz", "Dairy", 3.99, 227, True),
    ("Shredded Parmesan 8oz", "Dairy", 4.99, 227, True),
    ("Grated Parmesan 8oz", "Dairy", 4.49, 227, True),
    ("Parmesan Wedge 8oz", "Dairy", 7.99, 227, True),
    ("Feta Cheese Crumbles 6oz", "Dairy", 4.99, 170, True),
    ("Goat Cheese Log 4oz", "Dairy", 4.99, 113, True),
    ("Blue Cheese Crumbles 5oz", "Dairy", 4.99, 142, True),
    ("Brie Cheese Wheel 8oz", "Dairy", 6.99, 227, True),
    ("Camembert Cheese 8oz", "Dairy", 6.99, 227, True),
    ("String Cheese 12oz", "Dairy", 4.99, 340, True),
    ("String Cheese Mozzarella Singles", "Dairy", 3.99, 283, True),
    ("Babybel Mini Cheese 6ct", "Dairy", 4.49, 113, True),
    ("Cheese Slices American 12oz", "Dairy", 3.99, 340, True),
    ("Cheese Slices Cheddar 8oz", "Dairy", 3.99, 227, True),
    ("Cheese Slices Swiss 8oz", "Dairy", 4.49, 227, True),
    ("Cheese Slices Provolone 8oz", "Dairy", 4.29, 227, True),
    ("Unsalted Butter 1lb", "Dairy", 5.99, 454, True),
    ("Salted Butter 1lb", "Dairy", 5.99, 454, True),
    ("European Style Butter 8oz", "Dairy", 4.99, 227, True),
    ("Organic Butter 1lb", "Dairy", 7.99, 454, True),
    ("Whipped Butter 8oz", "Dairy", 3.99, 227, True),
    ("Butter Sticks 1lb", "Dairy", 5.99, 454, True),
    ("Margarine Spread 15oz", "Dairy", 2.99, 425, True),
    ("Plant Butter 13oz", "Dairy", 4.99, 369, True),
    ("Large Eggs Grade A 12ct", "Dairy", 3.99, 680, True),
    ("Large Eggs Grade AA 12ct", "Dairy", 4.49, 680, True),
    ("Extra Large Eggs 12ct", "Dairy", 4.99, 750, True),
    ("Medium Eggs 12ct", "Dairy", 3.49, 600, True),
    ("Organic Eggs Large 12ct", "Dairy", 6.99, 680, True),
    ("Free Range Eggs Large 12ct", "Dairy", 5.99, 680, True),
    ("Cage Free Eggs Large 12ct", "Dairy", 4.99, 680, True),
    ("Brown Eggs Large 12ct", "Dairy", 4.49, 680, True),
    ("Omega-3 Eggs Large 12ct", "Dairy", 5.49, 680, True),
    ("Large Eggs 18ct", "Dairy", 5.99, 1020, True),
    ("Egg Whites Liquid 16oz", "Dairy", 4.99, 454, True),
    ("Half Dozen Eggs", "Dairy", 2.49, 340, True),
    ("Almond Milk Original 64oz", "Dairy", 3.99, 1893, False),
    ("Almond Milk Vanilla 64oz", "Dairy", 3.99, 1893, False),
    ("Almond Milk Unsweetened 64oz", "Dairy", 3.99, 1893, False),
    ("Oat Milk Original 64oz", "Dairy", 4.49, 1893, False),
    ("Oat Milk Vanilla 64oz", "Dairy", 4.49, 1893, False),
    ("Soy Milk Original 64oz", "Dairy", 3.49, 1893, False),
    ("Coconut Milk Beverage 64oz", "Dairy", 3.99, 1893, False),

    # PRODUCE (200 products)
    ("Bananas", "Produce", 0.59, 118, True),
    ("Apples Gala", "Produce", 1.99, 182, True),
    ("Apples Fuji", "Produce", 1.99, 182, True),
    ("Apples Honeycrisp", "Produce", 2.49, 182, True),
    ("Apples Granny Smith", "Produce", 1.79, 182, True),
    ("Apples Red Delicious", "Produce", 1.69, 182, True),
    ("Oranges Navel", "Produce", 1.29, 140, True),
    ("Oranges Valencia", "Produce", 1.19, 131, True),
    ("Clementines 3lb Bag", "Produce", 5.99, 1361, True),
    ("Grapefruit Ruby Red", "Produce", 1.49, 246, True),
    ("Lemons", "Produce", 0.79, 58, True),
    ("Limes", "Produce", 0.69, 67, True),
    ("Strawberries 1lb", "Produce", 4.99, 454, True),
    ("Blueberries 6oz", "Produce", 3.99, 170, True),
    ("Raspberries 6oz", "Produce", 4.49, 170, True),
    ("Blackberries 6oz", "Produce", 4.49, 170, True),
    ("Grapes Red Seedless", "Produce", 2.99, 454, True),
    ("Grapes Green Seedless", "Produce", 2.99, 454, True),
    ("Watermelon Seedless", "Produce", 5.99, 4536, True),
    ("Cantaloupe", "Produce", 3.49, 850, True),
    ("Honeydew Melon", "Produce", 3.99, 1814, True),
    ("Pineapple", "Produce", 3.99, 905, True),
    ("Mango", "Produce", 1.49, 336, True),
    ("Avocado Hass", "Produce", 1.99, 201, True),
    ("Avocado Bag 4ct", "Produce", 6.99, 804, True),
    ("Pears Bartlett", "Produce", 1.79, 178, True),
    ("Pears Anjou", "Produce", 1.89, 230, True),
    ("Pears Bosc", "Produce", 1.99, 200, True),
    ("Peaches", "Produce", 1.99, 150, True),
    ("Nectarines", "Produce", 1.99, 142, True),
    ("Plums", "Produce", 1.79, 66, True),
    ("Cherries", "Produce", 5.99, 454, True),
    ("Kiwi Each", "Produce", 0.79, 76, True),
    ("Papaya", "Produce", 2.99, 500, True),
    ("Pomegranate", "Produce", 2.99, 282, True),
    ("Figs Fresh 8oz", "Produce", 4.99, 227, True),
    ("Dates Fresh 8oz", "Produce", 5.99, 227, True),
    ("Tomatoes On The Vine", "Produce", 2.49, 454, True),
    ("Tomatoes Roma", "Produce", 1.99, 454, True),
    ("Cherry Tomatoes Pint", "Produce", 2.99, 284, True),
    ("Grape Tomatoes Pint", "Produce", 2.99, 284, True),
    ("Heirloom Tomatoes", "Produce", 3.99, 454, True),
    ("Cucumbers English", "Produce", 1.49, 400, True),
    ("Cucumbers Persian 1lb", "Produce", 2.99, 454, True),
    ("Cucumbers Regular", "Produce", 0.99, 301, True),
    ("Bell Peppers Green", "Produce", 1.29, 164, True),
    ("Bell Peppers Red", "Produce", 1.99, 164, True),
    ("Bell Peppers Yellow", "Produce", 1.99, 164, True),
    ("Bell Peppers Orange", "Produce", 1.99, 164, True),
    ("Jalape\u00f1o Peppers", "Produce", 0.49, 14, True),
    ("Serrano Peppers", "Produce", 0.59, 6, True),
    ("Poblano Peppers", "Produce", 0.99, 17, True),
    ("Mini Bell Peppers 1lb", "Produce", 3.99, 454, True),
    ("Lettuce Iceberg", "Produce", 1.99, 539, True),
    ("Lettuce Romaine", "Produce", 2.49, 626, True),
    ("Lettuce Butter", "Produce", 2.99, 163, True),
    ("Lettuce Red Leaf", "Produce", 2.49, 163, True),
    ("Lettuce Green Leaf", "Produce", 2.49, 163, True),
    ("Spring Mix 5oz", "Produce", 3.99, 142, True),
    ("Baby Spinach 5oz", "Produce", 2.99, 142, True),
    ("Arugula 5oz", "Produce", 3.49, 142, True),
    ("Kale Bunch", "Produce", 2.49, 227, True),
    ("Collard Greens Bunch", "Produce", 2.49, 340, True),
    ("Swiss Chard Bunch", "Produce", 2.99, 227, True),
    ("Cabbage Green", "Produce", 1.99, 908, True),
    ("Cabbage Red", "Produce", 2.49, 794, True),
    ("Cabbage Napa", "Produce", 2.99, 1000, True),
    ("Broccoli Crown", "Produce", 2.49, 454, True),
    ("Cauliflower Head", "Produce", 2.99, 575, True),
    ("Brussels Sprouts 1lb", "Produce", 3.49, 454, True),
    ("Asparagus Bunch", "Produce", 3.99, 454, True),
    ("Green Beans 1lb", "Produce", 2.99, 454, True),
    ("Snap Peas 8oz", "Produce", 3.49, 227, True),
    ("Snow Peas 8oz", "Produce", 3.49, 227, True),
    ("Carrots 1lb", "Produce", 0.99, 454, True),
    ("Carrots Baby 1lb", "Produce", 1.99, 454, True),
    ("Carrots Organic Bunch", "Produce", 2.49, 454, True),
    ("Celery Bunch", "Produce", 1.99, 680, True),
    ("Celery Hearts", "Produce", 3.49, 454, True),
    ("Onions Yellow", "Produce", 0.99, 150, True),
    ("Onions White", "Produce", 0.99, 150, True),
    ("Onions Red", "Produce", 1.29, 150, True),
    ("Onions Sweet", "Produce", 1.49, 241, True),
    ("Shallots", "Produce", 1.99, 100, True),
    ("Scallions Bunch", "Produce", 0.99, 100, True),
    ("Leeks", "Produce", 2.49, 227, True),
    ("Garlic Bulb", "Produce", 0.69, 34, True),
    ("Garlic Peeled 6oz", "Produce", 3.99, 170, True),
    ("Ginger Root", "Produce", 2.99, 114, True),
    ("Potatoes Russet 5lb", "Produce", 3.99, 2268, True),
    ("Potatoes Red 3lb", "Produce", 3.49, 1361, True),
    ("Potatoes Yukon Gold 3lb", "Produce", 4.49, 1361, True),
    ("Potatoes Baby", "Produce", 3.99, 680, True),
    ("Sweet Potatoes", "Produce", 1.49, 130, True),
    ("Yams", "Produce", 1.49, 136, True),
    ("Beets Bunch", "Produce", 2.49, 454, True),
    ("Turnips", "Produce", 1.99, 156, True),
    ("Radishes Bunch", "Produce", 1.49, 227, True),
    ("Parsnips", "Produce", 2.49, 454, True),
    ("Rutabaga", "Produce", 1.99, 454, True),
    ("Jicama", "Produce", 1.99, 454, True),
    ("Squash Yellow", "Produce", 1.49, 196, True),
    ("Squash Zucchini", "Produce", 1.49, 196, True),
    ("Squash Butternut", "Produce", 2.49, 900, True),
    ("Squash Acorn", "Produce", 1.99, 450, True),
    ("Squash Spaghetti", "Produce", 3.99, 900, True),
    ("Pumpkin", "Produce", 4.99, 2000, True),
    ("Eggplant", "Produce", 1.99, 458, True),
    ("Eggplant Japanese", "Produce", 2.49, 227, True),
    ("Corn On The Cob Each", "Produce", 0.79, 250, True),
    ("Mushrooms White 8oz", "Produce", 2.49, 227, True),
    ("Mushrooms Crimini 8oz", "Produce", 2.99, 227, True),
    ("Mushrooms Portobello", "Produce", 3.99, 227, True),
    ("Mushrooms Shiitake 4oz", "Produce", 4.99, 113, True),
    ("Mushrooms Mixed 8oz", "Produce", 4.99, 227, True),
    ("Herbs Basil Fresh", "Produce", 2.49, 28, True),
    ("Herbs Cilantro Fresh", "Produce", 0.99, 28, True),
    ("Herbs Parsley Fresh", "Produce", 0.99, 28, True),
    ("Herbs Mint Fresh", "Produce", 2.49, 28, True),
    ("Herbs Dill Fresh", "Produce", 2.49, 28, True),
    ("Herbs Rosemary Fresh", "Produce", 2.99, 28, True),
    ("Herbs Thyme Fresh", "Produce", 2.99, 28, True),
    ("Herbs Oregano Fresh", "Produce", 2.99, 28, True),
    ("Herbs Sage Fresh", "Produce", 2.99, 28, True),
    ("Herbs Chives Fresh", "Produce", 2.49, 28, True),
    ("Bok Choy", "Produce", 2.49, 340, True),
    ("Watercress Bunch", "Produce", 2.99, 113, True),
    ("Radicchio", "Produce", 2.99, 227, True),
    ("Endive", "Produce", 2.99, 200, True),
    ("Fennel Bulb", "Produce", 2.99, 234, True),
    ("Artichokes", "Produce", 2.49, 128, True),
    ("Okra 1lb", "Produce", 3.99, 454, True),
    ("Rhubarb 1lb", "Produce", 3.49, 454, True),
    ("Kohlrabi", "Produce", 1.99, 140, True),
    ("Daikon Radish", "Produce", 1.99, 340, True),
    ("Lemongrass Stalk", "Produce", 1.49, 15, True),
    ("Salad Kit Caesar", "Produce", 3.99, 312, True),
    ("Salad Kit Asian", "Produce", 3.99, 340, True),
    ("Salad Kit Southwest", "Produce", 3.99, 340, True),
    ("Coleslaw Mix 14oz", "Produce", 1.99, 397, True),
    ("Stir Fry Vegetables 12oz", "Produce", 2.99, 340, True),
    ("Mixed Vegetables Cut 16oz", "Produce", 3.49, 454, True),
    ("Vegetable Tray with Dip", "Produce", 5.99, 454, True),
    ("Fruit Tray Mixed", "Produce", 7.99, 680, True),
    ("Guacamole Fresh 8oz", "Produce", 4.99, 227, True),
    ("Salsa Fresh Mild 16oz", "Produce", 3.99, 454, True),
    ("Hummus Original 10oz", "Produce", 3.99, 283, True),
    ("Hummus Roasted Red Pepper 10oz", "Produce", 3.99, 283, True),
    ("Hummus Garlic 10oz", "Produce", 3.99, 283, True),
    ("Pico de Gallo Fresh 16oz", "Produce", 3.99, 454, True),
    ("Bean Sprouts 8oz", "Produce", 1.99, 227, True),
    ("Alfalfa Sprouts 4oz", "Produce", 2.49, 113, True),
    ("Microgreens 2oz", "Produce", 3.99, 57, True),
    ("Edamame in Pod 12oz", "Produce", 2.99, 340, True),
    ("Tofu Firm 14oz", "Produce", 2.49, 397, True),
    ("Tofu Extra Firm 14oz", "Produce", 2.49, 397, True),
    ("Tofu Silken 14oz", "Produce", 2.49, 397, True),
    ("Tempeh 8oz", "Produce", 3.99, 227, True),
    ("Jackfruit Young Green 14oz", "Produce", 3.99, 397, True),
    ("Dragon Fruit", "Produce", 4.99, 400, True),
    ("Star Fruit", "Produce", 2.99, 91, True),
    ("Persimmon Fuyu", "Produce", 1.99, 168, True),
    ("Lychee 1lb", "Produce", 5.99, 454, True),
    ("Rambutan 1lb", "Produce", 5.99, 454, True),
    ("Passion Fruit Each", "Produce", 1.99, 18, True),
    ("Guava", "Produce", 1.99, 55, True),
    ("Plantains", "Produce", 0.99, 179, True),
    ("Coconut Whole", "Produce", 2.99, 397, True),
    ("Coconut Young Drinking", "Produce", 3.99, 450, True),
    ("Fresh Herbs 4pk", "Produce", 4.99, 112, True),

    # MEAT (100 products)
    ("Ground Beef 80/20 1lb", "Meat", 4.99, 454, True),
    ("Ground Beef 85/15 1lb", "Meat", 5.49, 454, True),
    ("Ground Beef 90/10 1lb", "Meat", 5.99, 454, True),
    ("Ground Beef 93/7 1lb", "Meat", 6.49, 454, True),
    ("Ground Turkey 1lb", "Meat", 4.49, 454, True),
    ("Ground Chicken 1lb", "Meat", 4.99, 454, True),
    ("Ground Pork 1lb", "Meat", 3.99, 454, True),
    ("Ground Lamb 1lb", "Meat", 7.99, 454, True),
    ("Beef Chuck Roast 2lb", "Meat", 12.99, 907, True),
    ("Beef Sirloin Steak 1lb", "Meat", 8.99, 454, True),
    ("Beef Ribeye Steak 1lb", "Meat", 12.99, 454, True),
    ("Beef T-Bone Steak 1lb", "Meat", 11.99, 454, True),
    ("Beef Filet Mignon 8oz", "Meat", 14.99, 227, True),
    ("Beef New York Strip 1lb", "Meat", 13.99, 454, True),
    ("Beef Flank Steak 1lb", "Meat", 9.99, 454, True),
    ("Beef Skirt Steak 1lb", "Meat", 10.99, 454, True),
    ("Beef Short Ribs 2lb", "Meat", 14.99, 907, True),
    ("Beef Stew Meat 1lb", "Meat", 6.99, 454, True),
    ("Beef Brisket 3lb", "Meat", 18.99, 1361, True),
    ("Beef Oxtail 2lb", "Meat", 12.99, 907, True),
    ("Chicken Breast Boneless 1lb", "Meat", 5.99, 454, True),
    ("Chicken Breast Bone-In 2lb", "Meat", 7.99, 907, True),
    ("Chicken Thighs Boneless 1lb", "Meat", 4.99, 454, True),
    ("Chicken Thighs Bone-In 2lb", "Meat", 5.99, 907, True),
    ("Chicken Drumsticks 2lb", "Meat", 4.99, 907, True),
    ("Chicken Wings 2lb", "Meat", 6.99, 907, True),
    ("Chicken Whole 4lb", "Meat", 7.99, 1814, True),
    ("Chicken Tenders 1lb", "Meat", 6.99, 454, True),
    ("Chicken Leg Quarters 3lb", "Meat", 5.99, 1361, True),
    ("Turkey Breast Boneless 2lb", "Meat", 11.99, 907, True),
    ("Turkey Ground Breast 1lb", "Meat", 5.99, 454, True),
    ("Turkey Whole 12lb", "Meat", 24.99, 5443, True),
    ("Duck Whole 5lb", "Meat", 29.99, 2268, True),
    ("Cornish Hen 1.5lb", "Meat", 4.99, 680, True),
    ("Pork Chops Bone-In 1lb", "Meat", 4.99, 454, True),
    ("Pork Chops Boneless 1lb", "Meat", 5.99, 454, True),
    ("Pork Tenderloin 1lb", "Meat", 7.99, 454, True),
    ("Pork Shoulder Roast 3lb", "Meat", 11.99, 1361, True),
    ("Pork Ribs Baby Back 2lb", "Meat", 12.99, 907, True),
    ("Pork Ribs Spare 3lb", "Meat", 10.99, 1361, True),
    ("Pork Belly 2lb", "Meat", 14.99, 907, True),
    ("Pork Sausage Links 1lb", "Meat", 4.99, 454, True),
    ("Pork Sausage Patties 1lb", "Meat", 4.99, 454, True),
    ("Italian Sausage Sweet 1lb", "Meat", 5.49, 454, True),
    ("Italian Sausage Hot 1lb", "Meat", 5.49, 454, True),
    ("Bratwurst 1lb", "Meat", 5.99, 454, True),
    ("Chorizo Mexican 1lb", "Meat", 4.99, 454, True),
    ("Kielbasa 1lb", "Meat", 5.49, 454, True),
    ("Andouille Sausage 1lb", "Meat", 6.99, 454, True),
    ("Bacon Regular 1lb", "Meat", 6.99, 454, True),
    ("Bacon Thick Cut 1lb", "Meat", 8.99, 454, True),
    ("Bacon Turkey 12oz", "Meat", 5.99, 340, True),
    ("Bacon Center Cut 12oz", "Meat", 7.99, 340, True),
    ("Canadian Bacon 8oz", "Meat", 5.49, 227, True),
    ("Pancetta 4oz", "Meat", 6.99, 113, True),
    ("Prosciutto 4oz", "Meat", 7.99, 113, True),
    ("Ham Bone-In 3lb", "Meat", 12.99, 1361, True),
    ("Ham Boneless 2lb", "Meat", 11.99, 907, True),
    ("Ham Sliced Deli Style 1lb", "Meat", 6.99, 454, True),
    ("Ham Honey 1lb", "Meat", 7.99, 454, True),
    ("Ham Black Forest 1lb", "Meat", 7.99, 454, True),
    ("Turkey Breast Deli Sliced 1lb", "Meat", 7.99, 454, True),
    ("Turkey Smoked Deli 1lb", "Meat", 7.99, 454, True),
    ("Roast Beef Deli 1lb", "Meat", 8.99, 454, True),
    ("Pastrami 1lb", "Meat", 9.99, 454, True),
    ("Corned Beef 1lb", "Meat", 8.99, 454, True),
    ("Salami Genoa 1lb", "Meat", 7.99, 454, True),
    ("Salami Hard 1lb", "Meat", 7.99, 454, True),
    ("Pepperoni Sliced 8oz", "Meat", 4.99, 227, True),
    ("Bologna 1lb", "Meat", 4.99, 454, True),
    ("Liverwurst 1lb", "Meat", 5.99, 454, True),
    ("Mortadella 1lb", "Meat", 7.99, 454, True),
    ("Hot Dogs Beef 1lb", "Meat", 4.99, 454, True),
    ("Hot Dogs All Beef 1lb", "Meat", 5.99, 454, True),
    ("Hot Dogs Turkey 1lb", "Meat", 4.99, 454, True),
    ("Hot Dogs Jumbo 1lb", "Meat", 6.99, 454, True),
    ("Lamb Chops 1lb", "Meat", 14.99, 454, True),
    ("Lamb Leg Bone-In 3lb", "Meat", 24.99, 1361, True),
    ("Lamb Shoulder 2lb", "Meat", 16.99, 907, True),
    ("Lamb Rack 1.5lb", "Meat", 22.99, 680, True),
    ("Veal Cutlets 1lb", "Meat", 12.99, 454, True),
    ("Veal Chops 1lb", "Meat", 14.99, 454, True),
    ("Beef Liver 1lb", "Meat", 3.99, 454, True),
    ("Chicken Liver 1lb", "Meat", 2.99, 454, True),
    ("Beef Tongue 2lb", "Meat", 12.99, 907, True),
    ("Beef Tripe 1lb", "Meat", 4.99, 454, True),
    ("Pork Hocks 2lb", "Meat", 5.99, 907, True),
    ("Pork Neck Bones 2lb", "Meat", 4.99, 907, True),
    ("Beef Marrow Bones 2lb", "Meat", 6.99, 907, True),
    ("Chicken Feet 1lb", "Meat", 2.99, 454, True),
    ("Chicken Gizzards 1lb", "Meat", 2.49, 454, True),
    ("Chicken Hearts 1lb", "Meat", 2.99, 454, True),
    ("Rabbit Whole 3lb", "Meat", 19.99, 1361, True),
    ("Quail Whole 12oz", "Meat", 8.99, 340, True),
    ("Venison Ground 1lb", "Meat", 12.99, 454, True),
    ("Bison Ground 1lb", "Meat", 11.99, 454, True),
    ("Goat Stew Meat 1lb", "Meat", 9.99, 454, True),

    # SEAFOOD (100 products)
    ("Salmon Fillet Atlantic 1lb", "Seafood", 12.99, 454, True),
    ("Salmon Fillet Sockeye 1lb", "Seafood", 14.99, 454, True),
    ("Salmon Fillet Coho 1lb", "Seafood", 13.99, 454, True),
    ("Salmon Whole Side 2lb", "Seafood", 24.99, 907, True),
    ("Tilapia Fillet 1lb", "Seafood", 6.99, 454, True),
    ("Cod Fillet 1lb", "Seafood", 9.99, 454, True),
    ("Halibut Fillet 1lb", "Seafood", 19.99, 454, True),
    ("Mahi Mahi Fillet 1lb", "Seafood", 11.99, 454, True),
    ("Swordfish Steak 1lb", "Seafood", 16.99, 454, True),
    ("Tuna Steak Yellowfin 1lb", "Seafood", 14.99, 454, True),
    ("Tuna Steak Ahi 1lb", "Seafood", 15.99, 454, True),
    ("Snapper Red Fillet 1lb", "Seafood", 12.99, 454, True),
    ("Sea Bass Chilean 1lb", "Seafood", 18.99, 454, True),
    ("Grouper Fillet 1lb", "Seafood", 13.99, 454, True),
    ("Flounder Fillet 1lb", "Seafood", 10.99, 454, True),
    ("Sole Fillet 1lb", "Seafood", 11.99, 454, True),
    ("Catfish Fillet 1lb", "Seafood", 7.99, 454, True),
    ("Trout Rainbow 1lb", "Seafood", 9.99, 454, True),
    ("Branzino Whole 1lb", "Seafood", 12.99, 454, True),
    ("Mackerel Whole 1lb", "Seafood", 8.99, 454, True),
    ("Sardines Fresh 1lb", "Seafood", 6.99, 454, True),
    ("Anchovies Fresh 8oz", "Seafood", 5.99, 227, True),
    ("Smelts 1lb", "Seafood", 7.99, 454, True),
    ("Perch Fillet 1lb", "Seafood", 9.99, 454, True),
    ("Walleye Fillet 1lb", "Seafood", 11.99, 454, True),
    ("Shrimp Jumbo 21-25 ct 1lb", "Seafood", 14.99, 454, True),
    ("Shrimp Large 31-40 ct 1lb", "Seafood", 11.99, 454, True),
    ("Shrimp Medium 41-50 ct 1lb", "Seafood", 9.99, 454, True),
    ("Shrimp Colossal 16-20 ct 1lb", "Seafood", 17.99, 454, True),
    ("Shrimp Cocktail Ring 1lb", "Seafood", 12.99, 454, True),
    ("Prawns Spot 1lb", "Seafood", 16.99, 454, True),
    ("Crab Legs Snow 1lb", "Seafood", 24.99, 454, True),
    ("Crab Legs King 1lb", "Seafood", 39.99, 454, True),
    ("Crab Dungeness Whole 2lb", "Seafood", 29.99, 907, True),
    ("Crab Blue Soft Shell 4oz", "Seafood", 7.99, 113, True),
    ("Crab Meat Lump 8oz", "Seafood", 19.99, 227, True),
    ("Crab Meat Claw 8oz", "Seafood", 14.99, 227, True),
    ("Lobster Tail 6oz", "Seafood", 12.99, 170, True),
    ("Lobster Whole Live 1.5lb", "Seafood", 24.99, 680, True),
    ("Crawfish Live 3lb", "Seafood", 14.99, 1361, True),
    ("Scallops Sea Large 1lb", "Seafood", 19.99, 454, True),
    ("Scallops Bay 1lb", "Seafood", 14.99, 454, True),
    ("Mussels Black 2lb", "Seafood", 7.99, 907, True),
    ("Clams Littleneck 2lb", "Seafood", 8.99, 907, True),
    ("Clams Manila 2lb", "Seafood", 9.99, 907, True),
    ("Clams Cherrystone 2lb", "Seafood", 7.99, 907, True),
    ("Oysters Fresh 1 Dozen", "Seafood", 18.99, 454, True),
    ("Oysters Shucked Pint", "Seafood", 14.99, 473, True),
    ("Squid Whole Cleaned 1lb", "Seafood", 8.99, 454, True),
    ("Calamari Tubes Rings 1lb", "Seafood", 9.99, 454, True),
    ("Octopus Whole 2lb", "Seafood", 16.99, 907, True),
    ("Conch Meat 1lb", "Seafood", 12.99, 454, True),
    ("Sea Urchin Uni 4oz", "Seafood", 19.99, 113, True),
    ("Abalone 8oz", "Seafood", 29.99, 227, True),
    ("Eel Unagi 1lb", "Seafood", 14.99, 454, True),
    ("Monkfish Fillet 1lb", "Seafood", 13.99, 454, True),
    ("Skate Wing 1lb", "Seafood", 11.99, 454, True),
    ("Frog Legs 1lb", "Seafood", 12.99, 454, True),
    ("Alligator Tail Meat 1lb", "Seafood", 19.99, 454, True),
    ("Salmon Smoked 4oz", "Seafood", 7.99, 113, True),
    ("Salmon Lox 4oz", "Seafood", 8.99, 113, True),
    ("Trout Smoked 8oz", "Seafood", 9.99, 227, True),
    ("Herring Pickled 12oz", "Seafood", 6.99, 340, True),
    ("Anchovies in Oil 2oz", "Seafood", 3.99, 57, True),
    ("Sardines Canned 4oz", "Seafood", 2.99, 113, False),
    ("Tuna Canned in Water 5oz", "Seafood", 1.99, 142, False),
    ("Tuna Canned in Oil 5oz", "Seafood", 2.49, 142, False),
    ("Salmon Canned 6oz", "Seafood", 3.99, 170, False),
    ("Mackerel Canned 4oz", "Seafood", 2.49, 113, False),
    ("Clams Canned 6.5oz", "Seafood", 3.49, 184, False),
    ("Oysters Canned Smoked 3oz", "Seafood", 4.99, 85, False),
    ("Crab Meat Canned 6oz", "Seafood", 5.99, 170, False),
    ("Shrimp Canned 4oz", "Seafood", 3.99, 113, False),
    ("Caviar Black 2oz", "Seafood", 49.99, 57, True),
    ("Caviar Red 4oz", "Seafood", 12.99, 113, True),
    ("Roe Tobiko 4oz", "Seafood", 9.99, 113, True),
    ("Roe Masago 4oz", "Seafood", 8.99, 113, True),
    ("Surimi Crab Sticks 1lb", "Seafood", 5.99, 454, True),
    ("Fish Sticks Frozen 24oz", "Seafood", 6.99, 680, False),
    ("Shrimp Breaded Frozen 1lb", "Seafood", 8.99, 454, False),
    ("Shrimp Popcorn Frozen 12oz", "Seafood", 7.99, 340, False),
    ("Calamari Fried Frozen 1lb", "Seafood", 9.99, 454, False),
    ("Crab Cakes Frozen 12oz", "Seafood", 11.99, 340, False),
    ("Salmon Burgers Frozen 12oz", "Seafood", 9.99, 340, False),
    ("Tuna Steaks Frozen 1lb", "Seafood", 12.99, 454, False),
    ("Cod Fillets Frozen 1lb", "Seafood", 8.99, 454, False),
    ("Tilapia Fillets Frozen 1lb", "Seafood", 6.99, 454, False),
    ("Swai Fillets Frozen 1lb", "Seafood", 5.99, 454, False),
    ("Pollock Fillets Frozen 1lb", "Seafood", 5.99, 454, False),
    ("Haddock Fillets Frozen 1lb", "Seafood", 9.99, 454, False),
    ("Sole Fillets Frozen 1lb", "Seafood", 10.99, 454, False),
    ("Flounder Fillets Frozen 1lb", "Seafood", 10.99, 454, False),
    ("Mahi Mahi Fillets Frozen 1lb", "Seafood", 11.99, 454, False),
    ("Swordfish Steaks Frozen 1lb", "Seafood", 15.99, 454, False),
    ("Seafood Mix Frozen 1lb", "Seafood", 11.99, 454, False),

    # FROZEN (150 products)
    ("Pizza Cheese 12inch", "Frozen", 4.99, 454, False),
    ("Pizza Pepperoni 12inch", "Frozen", 5.49, 500, False),
    ("Pizza Supreme 12inch", "Frozen", 6.99, 567, False),
    ("Pizza Margherita 12inch", "Frozen", 5.99, 454, False),
    ("Pizza Meat Lovers 12inch", "Frozen", 6.99, 600, False),
    ("Pizza Veggie 12inch", "Frozen", 5.99, 500, False),
    ("Pizza BBQ Chicken 12inch", "Frozen", 6.49, 550, False),
    ("Pizza Four Cheese 12inch", "Frozen", 5.49, 480, False),
    ("Pizza Rolls 40ct", "Frozen", 5.99, 680, False),
    ("Bagel Bites 9ct", "Frozen", 3.99, 198, False),
    ("Hot Pockets Pepperoni 2pk", "Frozen", 3.49, 226, False),
    ("Hot Pockets Ham Cheese 2pk", "Frozen", 3.49, 226, False),
    ("Lean Pockets Turkey 2pk", "Frozen", 3.99, 226, False),
    ("Corn Dogs 6ct", "Frozen", 4.99, 453, False),
    ("Mini Corn Dogs 20ct", "Frozen", 5.99, 567, False),
    ("Chicken Nuggets 32oz", "Frozen", 6.99, 907, False),
    ("Chicken Tenders 25oz", "Frozen", 7.99, 709, False),
    ("Popcorn Chicken 28oz", "Frozen", 6.99, 794, False),
    ("Chicken Wings Frozen 3lb", "Frozen", 11.99, 1361, False),
    ("Mozzarella Sticks 24oz", "Frozen", 6.99, 680, False),
    ("Jalape\u00f1o Poppers 18oz", "Frozen", 5.99, 510, False),
    ("Onion Rings 22oz", "Frozen", 4.99, 624, False),
    ("French Fries Regular 32oz", "Frozen", 3.99, 907, False),
    ("French Fries Crinkle 32oz", "Frozen", 3.99, 907, False),
    ("French Fries Steak 28oz", "Frozen", 4.49, 794, False),
    ("Sweet Potato Fries 20oz", "Frozen", 4.99, 567, False),
    ("Tater Tots 32oz", "Frozen", 3.99, 907, False),
    ("Hash Browns Patties 22oz", "Frozen", 3.99, 624, False),
    ("Hash Browns Shredded 32oz", "Frozen", 3.49, 907, False),
    ("Potato Skins 24oz", "Frozen", 5.99, 680, False),
    ("Mac and Cheese Bites 18oz", "Frozen", 5.49, 510, False),
    ("Burritos Bean Cheese 8pk", "Frozen", 6.99, 907, False),
    ("Burritos Beef Bean 8pk", "Frozen", 7.99, 1020, False),
    ("Quesadilla Cheese 2pk", "Frozen", 4.99, 340, False),
    ("Taquitos Beef 20ct", "Frozen", 6.99, 680, False),
    ("Empanadas Beef 6pk", "Frozen", 7.99, 567, False),
    ("Spring Rolls Vegetable 12oz", "Frozen", 4.99, 340, False),
    ("Egg Rolls Pork 6pk", "Frozen", 5.99, 454, False),
    ("Potstickers Pork 24oz", "Frozen", 6.99, 680, False),
    ("Dumplings Chicken 24oz", "Frozen", 7.99, 680, False),
    ("Samosas Vegetable 8oz", "Frozen", 4.99, 227, False),
    ("Waffles Homestyle 24oz", "Frozen", 3.49, 680, False),
    ("Waffles Blueberry 24oz", "Frozen", 3.99, 680, False),
    ("Waffles Buttermilk 24oz", "Frozen", 3.49, 680, False),
    ("Pancakes Buttermilk 24oz", "Frozen", 3.99, 680, False),
    ("French Toast Sticks 24oz", "Frozen", 4.49, 680, False),
    ("Breakfast Burritos 6pk", "Frozen", 6.99, 850, False),
    ("Breakfast Sandwiches Sausage 4pk", "Frozen", 5.99, 454, False),
    ("Breakfast Sandwiches Bacon 4pk", "Frozen", 5.99, 454, False),
    ("Jimmy Dean Croissants 4pk", "Frozen", 6.99, 340, False),
    ("Sausage Biscuits 4pk", "Frozen", 4.99, 340, False),
    ("Lasagna Meat 38oz", "Frozen", 8.99, 1077, False),
    ("Lasagna Vegetable 38oz", "Frozen", 7.99, 1077, False),
    ("Macaroni Cheese Family 40oz", "Frozen", 6.99, 1134, False),
    ("Chicken Alfredo 24oz", "Frozen", 7.99, 680, False),
    ("Beef Stroganoff 28oz", "Frozen", 8.99, 794, False),
    ("Salisbury Steak Dinner 16oz", "Frozen", 4.99, 454, False),
    ("Meatloaf Dinner 16oz", "Frozen", 4.99, 454, False),
    ("Fried Chicken Dinner 16oz", "Frozen", 5.99, 454, False),
    ("Turkey Dinner 16oz", "Frozen", 5.49, 454, False),
    ("Pot Roast Dinner 16oz", "Frozen", 5.99, 454, False),
    ("Chicken Pot Pie 10oz", "Frozen", 3.49, 283, False),
    ("Beef Pot Pie 10oz", "Frozen", 3.49, 283, False),
    ("Turkey Pot Pie 10oz", "Frozen", 3.49, 283, False),
    ("Shepherd's Pie 24oz", "Frozen", 6.99, 680, False),
    ("Ravioli Cheese 25oz", "Frozen", 5.99, 709, False),
    ("Tortellini Cheese 20oz", "Frozen", 5.99, 567, False),
    ("Gnocchi Potato 16oz", "Frozen", 4.99, 454, False),
    ("Pierogies Potato 16oz", "Frozen", 3.99, 454, False),
    ("Pierogies Cheese 16oz", "Frozen", 3.99, 454, False),
    ("Peas 16oz", "Frozen", 1.99, 454, False),
    ("Corn 16oz", "Frozen", 1.99, 454, False),
    ("Green Beans Cut 16oz", "Frozen", 1.99, 454, False),
    ("Mixed Vegetables 16oz", "Frozen", 2.49, 454, False),
    ("Broccoli Florets 16oz", "Frozen", 2.49, 454, False),
    ("Cauliflower Florets 16oz", "Frozen", 2.49, 454, False),
    ("Brussels Sprouts 14oz", "Frozen", 2.99, 397, False),
    ("Spinach Chopped 16oz", "Frozen", 2.49, 454, False),
    ("Collard Greens 16oz", "Frozen", 2.49, 454, False),
    ("Okra Cut 16oz", "Frozen", 2.99, 454, False),
    ("Edamame Shelled 12oz", "Frozen", 2.99, 340, False),
    ("Stir Fry Vegetables 16oz", "Frozen", 2.99, 454, False),
    ("California Blend 16oz", "Frozen", 2.49, 454, False),
    ("Normandy Blend 16oz", "Frozen", 2.49, 454, False),
    ("Italian Blend 16oz", "Frozen", 2.49, 454, False),
    ("Asian Vegetables 16oz", "Frozen", 2.99, 454, False),
    ("Butternut Squash Cubed 12oz", "Frozen", 3.49, 340, False),
    ("Sweet Potato Cubes 16oz", "Frozen", 3.49, 454, False),
    ("Riced Cauliflower 12oz", "Frozen", 2.99, 340, False),
    ("Zucchini Noodles 12oz", "Frozen", 3.49, 340, False),
    ("Strawberries Whole 16oz", "Frozen", 3.99, 454, False),
    ("Blueberries 16oz", "Frozen", 4.99, 454, False),
    ("Raspberries 12oz", "Frozen", 4.99, 340, False),
    ("Blackberries 12oz", "Frozen", 4.99, 340, False),
    ("Mixed Berries 16oz", "Frozen", 4.49, 454, False),
    ("Mango Chunks 16oz", "Frozen", 3.99, 454, False),
    ("Pineapple Chunks 16oz", "Frozen", 3.49, 454, False),
    ("Peaches Sliced 16oz", "Frozen", 3.49, 454, False),
    ("Cherries Dark Sweet 16oz", "Frozen", 4.99, 454, False),
    ("Smoothie Mix Berry 32oz", "Frozen", 5.99, 907, False),
    ("Smoothie Mix Tropical 32oz", "Frozen", 5.99, 907, False),
    ("Acai Puree 14oz", "Frozen", 7.99, 397, False),
    ("Banana Sliced 16oz", "Frozen", 3.99, 454, False),
    ("Ice Cream Vanilla 48oz", "Frozen", 4.99, 1361, False),
    ("Ice Cream Chocolate 48oz", "Frozen", 4.99, 1361, False),
    ("Ice Cream Strawberry 48oz", "Frozen", 4.99, 1361, False),
    ("Ice Cream Cookies Cream 48oz", "Frozen", 5.49, 1361, False),
    ("Ice Cream Mint Chip 48oz", "Frozen", 5.49, 1361, False),
    ("Ice Cream Cookie Dough 48oz", "Frozen", 5.99, 1361, False),
    ("Ice Cream Rocky Road 48oz", "Frozen", 5.49, 1361, False),
    ("Ice Cream Butter Pecan 48oz", "Frozen", 5.49, 1361, False),
    ("Ice Cream Neapolitan 48oz", "Frozen", 4.99, 1361, False),
    ("Gelato Vanilla 16oz", "Frozen", 5.99, 454, False),
    ("Gelato Chocolate 16oz", "Frozen", 5.99, 454, False),
    ("Sorbet Mango 16oz", "Frozen", 4.99, 454, False),
    ("Sorbet Raspberry 16oz", "Frozen", 4.99, 454, False),
    ("Sorbet Lemon 16oz", "Frozen", 4.99, 454, False),
    ("Sherbet Orange 48oz", "Frozen", 4.49, 1361, False),
    ("Sherbet Rainbow 48oz", "Frozen", 4.49, 1361, False),
    ("Frozen Yogurt Vanilla 16oz", "Frozen", 4.99, 454, False),
    ("Ice Cream Bars Vanilla 12pk", "Frozen", 5.99, 850, False),
    ("Ice Cream Sandwiches 12pk", "Frozen", 5.49, 793, False),
    ("Drumsticks 8pk", "Frozen", 6.99, 600, False),
    ("Klondike Bars 6pk", "Frozen", 5.99, 396, False),
    ("Popsicles Fruit 18pk", "Frozen", 4.99, 567, False),
    ("Fudge Bars 12pk", "Frozen", 4.49, 680, False),
    ("Ice Cream Cones 10pk", "Frozen", 6.99, 567, False),
    ("Cheesecake Plain 32oz", "Frozen", 9.99, 907, False),
    ("Cheesecake Strawberry 32oz", "Frozen", 10.99, 907, False),
    ("Pie Apple 38oz", "Frozen", 7.99, 1077, False),
    ("Pie Cherry 38oz", "Frozen", 7.99, 1077, False),
    ("Pie Pumpkin 36oz", "Frozen", 6.99, 1020, False),
    ("Pie Pecan 32oz", "Frozen", 8.99, 907, False),
    ("Cake Chocolate 32oz", "Frozen", 8.99, 907, False),
    ("Cake Vanilla 32oz", "Frozen", 8.99, 907, False),
    ("Brownies Chocolate 24oz", "Frozen", 6.99, 680, False),
    ("Cookie Dough Chocolate Chip 16oz", "Frozen", 4.99, 454, False),
    ("Cookie Dough Sugar 16oz", "Frozen", 4.99, 454, False),
    ("Cinnamon Rolls 5pk", "Frozen", 3.99, 360, False),
    ("Bread Dough White 3pk", "Frozen", 4.99, 907, False),
    ("Bread Dough Wheat 3pk", "Frozen", 5.49, 907, False),
    ("Dinner Rolls 24ct", "Frozen", 3.99, 680, False),
    ("Garlic Bread 16oz", "Frozen", 3.49, 454, False),
    ("Texas Toast Garlic 8pk", "Frozen", 2.99, 198, False),
    ("Croissants 4pk", "Frozen", 3.99, 227, False),
    ("Puff Pastry Sheets 2pk", "Frozen", 4.99, 397, False),
    ("Phyllo Dough 1lb", "Frozen", 4.49, 454, False),

    # SNACKS (200 products)
    ("Potato Chips Original 10oz", "Snacks", 3.99, 283, False),
    ("Potato Chips BBQ 10oz", "Snacks", 3.99, 283, False),
    ("Potato Chips Sour Cream 10oz", "Snacks", 3.99, 283, False),
    ("Potato Chips Salt Vinegar 10oz", "Snacks", 3.99, 283, False),
    ("Potato Chips Cheddar 10oz", "Snacks", 3.99, 283, False),
    ("Kettle Chips Sea Salt 8oz", "Snacks", 4.49, 227, False),
    ("Kettle Chips BBQ 8oz", "Snacks", 4.49, 227, False),
    ("Tortilla Chips Original 13oz", "Snacks", 3.49, 369, False),
    ("Tortilla Chips Nacho 13oz", "Snacks", 3.49, 369, False),
    ("Tortilla Chips Lime 13oz", "Snacks", 3.49, 369, False),
    ("Corn Chips Regular 10oz", "Snacks", 3.49, 283, False),
    ("Corn Chips Chili Cheese 10oz", "Snacks", 3.49, 283, False),
    ("Pita Chips Sea Salt 8oz", "Snacks", 3.99, 227, False),
    ("Pita Chips Garlic 8oz", "Snacks", 3.99, 227, False),
    ("Bagel Chips Everything 7oz", "Snacks", 3.99, 198, False),
    ("Veggie Straws 7oz", "Snacks", 3.49, 198, False),
    ("Veggie Chips 6oz", "Snacks", 3.99, 170, False),
    ("Popcorn Butter 3pk", "Snacks", 4.99, 270, False),
    ("Popcorn Movie Theater 6pk", "Snacks", 5.99, 540, False),
    ("Popcorn Kettle Corn 7oz", "Snacks", 3.99, 198, False),
    ("Popcorn Caramel 7oz", "Snacks", 4.49, 198, False),
    ("Popcorn Cheese 7oz", "Snacks", 3.99, 198, False),
    ("Popcorn White Cheddar 7oz", "Snacks", 4.49, 198, False),
    ("Rice Cakes Plain 4.9oz", "Snacks", 2.99, 139, False),
    ("Rice Cakes Caramel 6oz", "Snacks", 3.49, 170, False),
    ("Pretzels Twist 16oz", "Snacks", 2.99, 454, False),
    ("Pretzels Rods 12oz", "Snacks", 3.49, 340, False),
    ("Pretzels Mini 16oz", "Snacks", 2.99, 454, False),
    ("Pretzels Honey Mustard 10oz", "Snacks", 3.99, 283, False),
    ("Crackers Saltine 16oz", "Snacks", 2.49, 454, False),
    ("Crackers Ritz 13.7oz", "Snacks", 3.99, 388, False),
    ("Crackers Wheat Thins 9oz", "Snacks", 3.49, 255, False),
    ("Crackers Triscuit 9oz", "Snacks", 3.49, 255, False),
    ("Crackers Cheez-It 12.4oz", "Snacks", 4.49, 352, False),
    ("Crackers Goldfish 30oz", "Snacks", 6.99, 850, False),
    ("Crackers Club 13.7oz", "Snacks", 3.99, 388, False),
    ("Crackers Town House 13.8oz", "Snacks", 3.99, 391, False),
    ("Crackers Graham Honey 14.4oz", "Snacks", 2.99, 408, False),
    ("Crackers Graham Chocolate 14.4oz", "Snacks", 2.99, 408, False),
    ("Crackers Graham Cinnamon 14.4oz", "Snacks", 2.99, 408, False),
    ("Nuts Mixed 16oz", "Snacks", 7.99, 454, False),
    ("Nuts Almonds Raw 16oz", "Snacks", 7.99, 454, False),
    ("Nuts Almonds Roasted 16oz", "Snacks", 8.49, 454, False),
    ("Nuts Cashews Roasted 16oz", "Snacks", 9.99, 454, False),
    ("Nuts Peanuts Roasted 16oz", "Snacks", 5.99, 454, False),
    ("Nuts Peanuts Honey Roasted 16oz", "Snacks", 6.49, 454, False),
    ("Nuts Walnuts Halves 16oz", "Snacks", 9.99, 454, False),
    ("Nuts Pecans Halves 16oz", "Snacks", 11.99, 454, False),
    ("Nuts Pistachios Roasted 16oz", "Snacks", 10.99, 454, False),
    ("Nuts Macadamia Roasted 8oz", "Snacks", 12.99, 227, False),
    ("Nuts Hazelnuts 8oz", "Snacks", 8.99, 227, False),
    ("Nuts Brazil 12oz", "Snacks", 9.99, 340, False),
    ("Nuts Pine 4oz", "Snacks", 11.99, 113, False),
    ("Trail Mix Classic 16oz", "Snacks", 6.99, 454, False),
    ("Trail Mix Energy 16oz", "Snacks", 7.99, 454, False),
    ("Trail Mix Tropical 14oz", "Snacks", 6.99, 397, False),
    ("Peanuts in Shell 2lb", "Snacks", 5.99, 907, False),
    ("Sunflower Seeds 16oz", "Snacks", 4.99, 454, False),
    ("Pumpkin Seeds 12oz", "Snacks", 5.99, 340, False),
    ("Raisins 15oz", "Snacks", 3.99, 425, False),
    ("Cranberries Dried 12oz", "Snacks", 4.99, 340, False),
    ("Apricots Dried 8oz", "Snacks", 5.99, 227, False),
    ("Prunes Dried 12oz", "Snacks", 4.99, 340, False),
    ("Dates Pitted 8oz", "Snacks", 4.99, 227, False),
    ("Cookies Chocolate Chip 12oz", "Snacks", 3.99, 340, False),
    ("Cookies Oreo 14.3oz", "Snacks", 4.49, 405, False),
    ("Cookies Chips Ahoy 13oz", "Snacks", 3.99, 369, False),
    ("Cookies Nutter Butter 16oz", "Snacks", 3.99, 454, False),
    ("Cookies Vienna Fingers 14.3oz", "Snacks", 3.49, 405, False),
    ("Cookies Fig Newtons 10oz", "Snacks", 3.99, 283, False),
    ("Cookies Vanilla Wafers 11oz", "Snacks", 2.99, 312, False),
    ("Cookies Animal Crackers 16oz", "Snacks", 2.99, 454, False),
    ("Cookies Ginger Snaps 16oz", "Snacks", 2.99, 454, False),
    ("Cookies Graham Crackers 14.4oz", "Snacks", 2.99, 408, False),
    ("Granola Bars Chewy Chocolate Chip 10ct", "Snacks", 3.99, 250, False),
    ("Granola Bars Crunchy Oats 12ct", "Snacks", 3.99, 300, False),
    ("Granola Bars Peanut Butter 10ct", "Snacks", 4.49, 250, False),
    ("Protein Bars Chocolate 12ct", "Snacks", 11.99, 600, False),
    ("Protein Bars Peanut Butter 12ct", "Snacks", 11.99, 600, False),
    ("Fruit Snacks Mixed Berry 10ct", "Snacks", 3.49, 250, False),
    ("Fruit Snacks Strawberry 10ct", "Snacks", 3.49, 250, False),
    ("Applesauce Cups 6pk", "Snacks", 2.99, 600, False),
    ("Pudding Cups Chocolate 4pk", "Snacks", 2.49, 450, False),
    ("Pudding Cups Vanilla 4pk", "Snacks", 2.49, 450, False),
    ("Jello Cups Cherry 4pk", "Snacks", 1.99, 400, False),
    ("Jello Cups Strawberry 4pk", "Snacks", 1.99, 400, False),
    ("Candy Bar Snickers", "Snacks", 1.29, 52, False),
    ("Candy Bar Milky Way", "Snacks", 1.29, 52, False),
    ("Candy Bar 3 Musketeers", "Snacks", 1.29, 54, False),
    ("Candy Bar Twix", "Snacks", 1.29, 50, False),
    ("Candy Bar Kit Kat", "Snacks", 1.29, 42, False),
    ("Candy Bar Hershey Milk Chocolate", "Snacks", 1.29, 43, False),
    ("Candy Bar Reese's Peanut Butter Cup", "Snacks", 1.29, 42, False),
    ("Candy M&M Peanut 10oz", "Snacks", 4.99, 283, False),
    ("Candy M&M Milk Chocolate 10oz", "Snacks", 4.99, 283, False),
    ("Candy Skittles 14oz", "Snacks", 3.99, 397, False),
    ("Candy Starburst 14oz", "Snacks", 3.99, 397, False),
    ("Candy Gummy Bears 14oz", "Snacks", 3.49, 397, False),
    ("Candy Sour Gummy Worms 14oz", "Snacks", 3.49, 397, False),
    ("Candy Swedish Fish 14oz", "Snacks", 3.49, 397, False),
    ("Candy Licorice Red 16oz", "Snacks", 3.99, 454, False),
    ("Candy Licorice Black 16oz", "Snacks", 3.99, 454, False),
    ("Gum Spearmint 15ct", "Snacks", 1.99, 35, False),
    ("Gum Peppermint 15ct", "Snacks", 1.99, 35, False),

    # PERSONAL CARE (100 products)
    ("Shampoo Regular 12oz", "Personal Care", 4.99, 355, False),
    ("Shampoo Moisturizing 12oz", "Personal Care", 5.99, 355, False),
    ("Shampoo Volumizing 12oz", "Personal Care", 5.99, 355, False),
    ("Shampoo Dandruff 12oz", "Personal Care", 6.99, 355, False),
    ("Shampoo Color Safe 12oz", "Personal Care", 6.49, 355, False),
    ("Conditioner Regular 12oz", "Personal Care", 4.99, 355, False),
    ("Conditioner Moisturizing 12oz", "Personal Care", 5.99, 355, False),
    ("Conditioner Volumizing 12oz", "Personal Care", 5.99, 355, False),
    ("Conditioner Repair 12oz", "Personal Care", 6.49, 355, False),
    ("2-in-1 Shampoo & Conditioner 12oz", "Personal Care", 5.49, 355, False),
    ("Body Wash Original 18oz", "Personal Care", 4.99, 532, False),
    ("Body Wash Moisturizing 18oz", "Personal Care", 5.49, 532, False),
    ("Body Wash Sport 18oz", "Personal Care", 5.49, 532, False),
    ("Body Wash Sensitive Skin 18oz", "Personal Care", 5.99, 532, False),
    ("Bar Soap Original 4pk", "Personal Care", 3.99, 400, False),
    ("Bar Soap Moisturizing 4pk", "Personal Care", 4.49, 400, False),
    ("Bar Soap Antibacterial 4pk", "Personal Care", 4.49, 400, False),
    ("Hand Soap Liquid 7.5oz", "Personal Care", 2.49, 221, False),
    ("Hand Soap Antibacterial 7.5oz", "Personal Care", 2.99, 221, False),
    ("Hand Soap Foam 8.5oz", "Personal Care", 3.49, 251, False),
    ("Hand Sanitizer Gel 8oz", "Personal Care", 3.99, 237, False),
    ("Hand Sanitizer Spray 2oz", "Personal Care", 2.99, 59, False),
    ("Toothpaste Whitening 6oz", "Personal Care", 3.99, 170, False),
    ("Toothpaste Sensitive 4oz", "Personal Care", 4.99, 113, False),
    ("Toothpaste Cavity Protection 6oz", "Personal Care", 3.49, 170, False),
    ("Toothpaste Fresh Mint 6oz", "Personal Care", 3.49, 170, False),
    ("Toothpaste Tartar Control 6oz", "Personal Care", 3.99, 170, False),
    ("Toothbrush Soft 2pk", "Personal Care", 3.99, 50, False),
    ("Toothbrush Medium 2pk", "Personal Care", 3.99, 50, False),
    ("Mouthwash Mint 1L", "Personal Care", 5.99, 1000, False),
    ("Mouthwash Antiseptic 1L", "Personal Care", 6.49, 1000, False),
    ("Dental Floss 50 yards", "Personal Care", 2.99, 45, False),
    ("Deodorant Men''s 2.7oz", "Personal Care", 4.99, 76, False),
    ("Deodorant Women''s 2.6oz", "Personal Care", 4.99, 74, False),
    ("Deodorant Clinical Strength 1.7oz", "Personal Care", 8.99, 48, False),
    ("Antiperspirant Men''s 2.7oz", "Personal Care", 5.49, 76, False),
    ("Antiperspirant Women''s 2.6oz", "Personal Care", 5.49, 74, False),
    ("Razors Disposable Men''s 10ct", "Personal Care", 7.99, 100, False),
    ("Razors Disposable Women''s 8ct", "Personal Care", 7.99, 80, False),
    ("Razors Cartridges Men''s 4ct", "Personal Care", 14.99, 40, False),
    ("Razors Cartridges Women''s 4ct", "Personal Care", 14.99, 40, False),
    ("Shaving Cream Men''s 7oz", "Personal Care", 3.49, 198, False),
    ("Shaving Cream Women''s 7oz", "Personal Care", 3.49, 198, False),
    ("Shaving Gel Men''s 7oz", "Personal Care", 3.99, 198, False),
    ("Toilet Paper 12 Rolls", "Personal Care", 7.99, 1200, False),
    ("Toilet Paper 24 Rolls", "Personal Care", 14.99, 2400, False),
    ("Paper Towels 6 Rolls", "Personal Care", 9.99, 1200, False),
    ("Facial Tissue 6 Boxes", "Personal Care", 7.99, 900, False),
    ("Cotton Swabs 500ct", "Personal Care", 3.99, 150, False),
    ("Baby Wipes 80ct", "Personal Care", 3.49, 400, False),
]

# NYC-focused location data
NYC_ZONES = [
    ("BK", "Brooklyn", ["Atlantic Ave", "Court St", "Flatbush Ave", "Smith St", "Bedford Ave"]),
    ("MAN", "Manhattan", ["Broadway", "5th Ave", "Madison Ave", "Park Ave", "Lexington Ave"]),
    ("QNS", "Queens", ["Steinway St", "Queens Blvd", "Jamaica Ave", "Roosevelt Ave", "Northern Blvd"]),
    ("BX", "Bronx", ["Grand Concourse", "Fordham Rd", "E Tremont Ave", "Webster Ave", "3rd Ave"]),
    ("SI", "Staten Island", ["Victory Blvd", "Forest Ave", "Hylan Blvd", "Richmond Ave", "Bay St"]),
]

ORDER_STATUSES = ["CREATED", "DELIVERED", "CANCELLED"]
COURIER_STATUSES = ["OFF_SHIFT", "AVAILABLE", "ON_DELIVERY"]
VEHICLE_TYPES = ["BIKE", "SCOOTER", "CAR", "WALKING"]
TASK_STATUSES = ["PENDING", "IN_PROGRESS", "COMPLETED", "FAILED"]


class DataGenerator:
    """Generates FreshMart load test data."""

    def __init__(self, scale: float = 1.0):
        self.scale = scale
        self.triples: List[Tuple[str, str, str, str]] = []

        # Scaled counts
        self.num_stores = max(10, int(50 * scale))
        self.num_products = len(REALISTIC_PRODUCTS)  # Use all realistic products (993)
        self.num_customers = max(100, int(5000 * scale))
        self.num_couriers = max(self.num_stores * 15, int(200 * scale))  # At least 15 couriers per store
        self.num_orders = max(500, int(25000 * scale))
        self.lines_per_order = 3  # Average
        self.num_days = 180  # 6 months

        # Generated IDs for reference
        self.store_ids: List[str] = []
        self.product_ids: List[str] = []
        self.customer_ids: List[str] = []
        self.courier_ids: List[str] = []
        self.order_ids: List[str] = []

        # Store-courier mapping for realistic assignments
        self.store_couriers: dict = {}

    def add_triple(self, subject_id: str, predicate: str, object_value: str, object_type: str):
        """Add a triple to the batch."""
        self.triples.append((subject_id, predicate, str(object_value), object_type))

    def generate_stores(self):
        """Generate store entities."""
        print(f"Generating {self.num_stores} stores...")

        stores_per_zone = max(1, self.num_stores // len(NYC_ZONES))
        store_num = 1

        for zone_code, zone_name, streets in NYC_ZONES:
            for i in range(stores_per_zone):
                if store_num > self.num_stores:
                    break

                store_id = f"store:{zone_code}-{i+1:02d}"
                self.store_ids.append(store_id)

                street = random.choice(streets)
                address = f"{random.randint(100, 999)} {street}, {zone_name}, NY {fake.zipcode_in_state('NY')}"

                self.add_triple(store_id, "store_name", f"FreshMart {zone_name} {i+1}", "string")
                self.add_triple(store_id, "store_address", address, "string")
                self.add_triple(store_id, "store_zone", zone_code, "string")
                self.add_triple(store_id, "store_status", random.choice(["OPEN", "OPEN", "OPEN", "LIMITED"]), "string")
                self.add_triple(store_id, "store_capacity_orders_per_hour", str(random.randint(30, 80)), "int")

                store_num += 1

    def generate_products(self):
        """Generate product entities using realistic catalog."""
        print(f"Generating all {len(REALISTIC_PRODUCTS)} products (products never scale)...")

        # Always use ALL realistic products regardless of scale parameter
        # REALISTIC_PRODUCTS format: (name, category, price, weight_grams, perishable)
        products_to_use = REALISTIC_PRODUCTS

        for product_num, (name, category, price, weight_grams, perishable) in enumerate(products_to_use, start=1):
            # Create consistent product ID
            product_id = f"product:prod{product_num:04d}"
            self.product_ids.append(product_id)

            self.add_triple(product_id, "product_name", name, "string")
            self.add_triple(product_id, "category", category, "string")
            self.add_triple(product_id, "unit_price", f"{price:.2f}", "float")
            self.add_triple(product_id, "unit_weight_grams", str(weight_grams), "int")
            self.add_triple(product_id, "perishable", str(perishable).lower(), "bool")

    def generate_customers(self):
        """Generate customer entities."""
        print(f"Generating {self.num_customers} customers...")

        for i in range(self.num_customers):
            customer_id = f"customer:{i+1:05d}"
            self.customer_ids.append(customer_id)

            zone = random.choice(NYC_ZONES)
            street = random.choice(zone[2])

            self.add_triple(customer_id, "customer_name", fake.name(), "string")
            self.add_triple(customer_id, "customer_email", fake.email(), "string")
            self.add_triple(customer_id, "customer_address",
                          f"{fake.building_number()} {street}, {zone[1]}, NY {fake.zipcode_in_state('NY')}",
                          "string")

    def generate_couriers(self):
        """Generate courier entities."""
        print(f"Generating {self.num_couriers} couriers...")

        couriers_per_store = max(15, self.num_couriers // len(self.store_ids))
        courier_num = 1

        for store_id in self.store_ids:
            self.store_couriers[store_id] = []

            for i in range(couriers_per_store):
                if courier_num > self.num_couriers:
                    break

                courier_id = f"courier:C-{courier_num:04d}"
                self.courier_ids.append(courier_id)
                self.store_couriers[store_id].append(courier_id)

                self.add_triple(courier_id, "courier_name", fake.name(), "string")
                self.add_triple(courier_id, "courier_home_store", store_id, "entity_ref")
                self.add_triple(courier_id, "vehicle_type", random.choice(VEHICLE_TYPES), "string")
                self.add_triple(courier_id, "courier_status", "AVAILABLE", "string")

                courier_num += 1

    def generate_inventory(self):
        """Generate inventory items for each store."""
        print(f"Generating inventory for {len(self.store_ids)} stores...")

        inventory_num = 1
        # All products available in all stores (1000 products per store)
        products_per_store = len(self.product_ids)

        for store_id in self.store_ids:
            # Each store carries all products
            store_products = self.product_ids

            for product_id in store_products:
                inventory_id = f"inventory:INV-{inventory_num:06d}"

                stock = random.randint(0, 100)

                self.add_triple(inventory_id, "inventory_store", store_id, "entity_ref")
                self.add_triple(inventory_id, "inventory_product", product_id, "entity_ref")
                self.add_triple(inventory_id, "stock_level", str(stock), "int")

                # Add replenishment ETA for low stock items
                if stock < 10:
                    eta = datetime.now() + timedelta(hours=random.randint(4, 48))
                    self.add_triple(inventory_id, "replenishment_eta", eta.isoformat(), "timestamp")

                inventory_num += 1

    def generate_orders(self):
        """Generate orders with order lines and delivery tasks."""
        print(f"Generating {self.num_orders} orders with order lines and delivery tasks...")

        # Distribute orders across the time period
        start_date = datetime.now() - timedelta(days=self.num_days)

        for i in range(self.num_orders):
            if i % 5000 == 0 and i > 0:
                print(f"  Generated {i} orders...")

            order_id = f"order:FM-{i+1:06d}"
            self.order_ids.append(order_id)

            # Random date within the period, weighted toward recent
            days_ago = int(random.triangular(0, self.num_days, self.num_days * 0.3))
            order_date = datetime.now() - timedelta(days=days_ago)

            # Peak hours: 11am-1pm, 5pm-8pm
            hour = random.choices(
                range(24),
                weights=[1,1,1,1,1,1,1,2,3,4,5,8,8,5,4,3,4,6,8,8,6,4,2,1]
            )[0]
            order_date = order_date.replace(hour=hour, minute=random.randint(0, 59))

            # Assign to store and customer
            store_id = random.choice(self.store_ids)
            customer_id = random.choice(self.customer_ids)

            # Delivery window (1-2 hours from order)
            window_start = order_date + timedelta(hours=random.uniform(0.5, 1.5))
            window_end = window_start + timedelta(hours=random.uniform(1, 2))

            # Status based on age
            if days_ago > 2:
                status = random.choices(
                    ORDER_STATUSES,
                    weights=[1, 90, 6]  # Mostly delivered
                )[0]
            elif days_ago > 0:
                status = random.choices(
                    ORDER_STATUSES,
                    weights=[5, 60, 5]
                )[0]
            else:  # Today
                status = random.choices(
                    ORDER_STATUSES,
                    weights=[30, 15, 5]  # Mostly created, waiting for courier
                )[0]

            # Generate order lines first to calculate total
            num_lines = random.randint(1, 6)
            line_products = random.sample(self.product_ids, min(num_lines, len(self.product_ids)))

            order_total = Decimal("0.00")
            for line_num, product_id in enumerate(line_products, 1):
                # Use UUID-based line IDs (consistent with order_line_service.py)
                line_uuid = str(uuid.uuid4())
                line_id = f"orderline:{line_uuid}"
                quantity = random.randint(1, 4)
                # Get a reasonable price
                unit_price = Decimal(str(random.uniform(2.0, 15.0))).quantize(Decimal("0.01"))
                line_total = unit_price * quantity
                order_total += line_total

                self.add_triple(line_id, "line_of_order", order_id, "entity_ref")
                self.add_triple(line_id, "line_product", product_id, "entity_ref")
                self.add_triple(line_id, "quantity", str(quantity), "int")
                self.add_triple(line_id, "order_line_unit_price", str(unit_price), "float")
                self.add_triple(line_id, "line_amount", str(line_total), "float")
                self.add_triple(line_id, "line_sequence", str(line_num), "int")

            # Order triples
            self.add_triple(order_id, "order_number", f"FM-{i+1:06d}", "string")
            self.add_triple(order_id, "order_status", status, "string")
            self.add_triple(order_id, "order_store", store_id, "entity_ref")
            self.add_triple(order_id, "placed_by", customer_id, "entity_ref")
            self.add_triple(order_id, "delivery_window_start", window_start.isoformat(), "timestamp")
            self.add_triple(order_id, "delivery_window_end", window_end.isoformat(), "timestamp")
            self.add_triple(order_id, "order_total_amount", str(order_total), "float")
            self.add_triple(order_id, "order_created_at", order_date.isoformat(), "timestamp")

            # Generate delivery task for non-cancelled orders
            if status != "CANCELLED":
                task_id = f"task:T-{i+1:06d}"

                # Assign courier from the store
                store_couriers = self.store_couriers.get(store_id, self.courier_ids)
                courier_id = random.choice(store_couriers) if store_couriers else random.choice(self.courier_ids)

                # Task status mirrors order status
                if status == "DELIVERED":
                    task_status = "COMPLETED"
                elif status == "OUT_FOR_DELIVERY":
                    task_status = "IN_PROGRESS"
                else:
                    task_status = "PENDING"

                self.add_triple(task_id, "task_of_order", order_id, "entity_ref")
                self.add_triple(task_id, "assigned_to", courier_id, "entity_ref")
                self.add_triple(task_id, "task_status", task_status, "string")

                if status in ["OUT_FOR_DELIVERY", "DELIVERED"]:
                    eta = window_start + timedelta(minutes=random.randint(-15, 30))
                    self.add_triple(task_id, "eta", eta.isoformat(), "timestamp")
                    self.add_triple(task_id, "route_sequence", str(random.randint(1, 5)), "int")

    def generate_all(self):
        """Generate all entity types."""
        self.generate_stores()
        self.generate_products()
        self.generate_customers()
        self.generate_couriers()
        self.generate_inventory()
        self.generate_orders()

        return self.triples

    def get_statistics(self) -> dict:
        """Return statistics about generated data."""
        return {
            "scale_factor": self.scale,
            "stores": self.num_stores,
            "products": self.num_products,
            "customers": self.num_customers,
            "couriers": self.num_couriers,
            "orders": self.num_orders,
            "estimated_order_lines": self.num_orders * self.lines_per_order,
            "estimated_delivery_tasks": int(self.num_orders * 0.94),  # ~6% cancelled
            "estimated_inventory_items": self.num_stores * min(len(self.product_ids), int(200 * self.scale)),
            "total_triples": len(self.triples),
        }


def get_db_connection():
    """Create database connection from environment variables."""
    return psycopg2.connect(
        host=os.environ.get("PG_HOST", "localhost"),
        port=int(os.environ.get("PG_PORT", 5432)),
        user=os.environ.get("PG_USER", "postgres"),
        password=os.environ.get("PG_PASSWORD", "postgres"),
        database=os.environ.get("PG_DATABASE", "freshmart"),
    )


def clear_demo_data(conn):
    """Clear existing demo data (keeps ontology)."""
    print("Clearing existing triple data...")
    with conn.cursor() as cur:
        cur.execute("DELETE FROM triples")
        deleted = cur.rowcount
        conn.commit()
        print(f"  Deleted {deleted} existing triples")


def insert_triples(conn, triples: List[Tuple], batch_size: int = 1000):
    """Insert triples in batches."""
    print(f"Inserting {len(triples)} triples in batches of {batch_size}...")

    with conn.cursor() as cur:
        for i in range(0, len(triples), batch_size):
            batch = triples[i:i + batch_size]
            execute_values(
                cur,
                """
                INSERT INTO triples (subject_id, predicate, object_value, object_type)
                VALUES %s
                """,
                batch,
                template="(%s, %s, %s, %s)"
            )

            if (i + batch_size) % 50000 == 0 or i + batch_size >= len(triples):
                conn.commit()
                print(f"  Inserted {min(i + batch_size, len(triples))} triples...")

    conn.commit()
    print("  Done!")


def run_analyze(conn):
    """Run ANALYZE to update table statistics."""
    print("Running ANALYZE on triples table...")
    conn.autocommit = True
    with conn.cursor() as cur:
        cur.execute("ANALYZE triples")
    conn.autocommit = False
    print("  Done!")


def main():
    parser = argparse.ArgumentParser(
        description="Generate FreshMart load test data",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Generate full dataset (~700K triples)
  python generate_load_test_data.py

  # Generate smaller dataset for testing (~70K triples)
  python generate_load_test_data.py --scale 0.1

  # Clear and regenerate
  python generate_load_test_data.py --clear

  # Preview without inserting
  python generate_load_test_data.py --dry-run
        """
    )
    parser.add_argument("--scale", type=float, default=1.0,
                       help="Scale factor (1.0 = ~700K triples)")
    parser.add_argument("--clear", action="store_true",
                       help="Clear existing data before generating")
    parser.add_argument("--dry-run", action="store_true",
                       help="Print statistics without inserting")
    parser.add_argument("--batch-size", type=int, default=1000,
                       help="Batch size for inserts")

    args = parser.parse_args()

    print("=" * 60)
    print("FreshMart Load Test Data Generator")
    print("=" * 60)
    print()

    # Generate data
    generator = DataGenerator(scale=args.scale)
    triples = generator.generate_all()

    # Print statistics
    stats = generator.get_statistics()
    print()
    print("Generated Data Statistics:")
    print("-" * 40)
    print(f"  Scale factor:        {stats['scale_factor']}")
    print(f"  Stores:              {stats['stores']:,}")
    print(f"  Products:            {stats['products']:,}")
    print(f"  Customers:           {stats['customers']:,}")
    print(f"  Couriers:            {stats['couriers']:,}")
    print(f"  Orders:              {stats['orders']:,}")
    print(f"  Order Lines:         ~{stats['estimated_order_lines']:,}")
    print(f"  Delivery Tasks:      ~{stats['estimated_delivery_tasks']:,}")
    print(f"  Inventory Items:     ~{stats['estimated_inventory_items']:,}")
    print("-" * 40)
    print(f"  TOTAL TRIPLES:       {stats['total_triples']:,}")
    print()

    if args.dry_run:
        print("Dry run - no data inserted")
        return

    # Connect and insert
    try:
        conn = get_db_connection()
        print(f"Connected to PostgreSQL at {os.environ.get('PG_HOST', 'localhost')}:{os.environ.get('PG_PORT', 5432)}")
        print()

        if args.clear:
            clear_demo_data(conn)
            print()

        insert_triples(conn, triples, batch_size=args.batch_size)
        print()

        run_analyze(conn)
        print()

        # Verify count
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM triples")
            total = cur.fetchone()[0]
            print(f"Total triples in database: {total:,}")

        conn.close()

    except psycopg2.Error as e:
        print(f"Database error: {e}")
        sys.exit(1)

    print()
    print("=" * 60)
    print("Data generation complete!")
    print()
    print("Materialize views update automatically via CDC.")
    print()
    print("Next steps:")
    print("  1. Verify data in Materialize (may take a few seconds to sync):")
    print("     PGPASSWORD=materialize psql -h localhost -p 6875 -U materialize -c \\")
    print('       "SET CLUSTER = serving; SELECT COUNT(*) FROM orders_flat_mv;"')
    print()
    print("  2. Test query performance:")
    print("     curl http://localhost:8080/freshmart/orders | head")
    print()
    print("  3. Compare PostgreSQL vs Materialize:")
    print("     curl http://localhost:8080/stats")
    print("=" * 60)


if __name__ == "__main__":
    main()
