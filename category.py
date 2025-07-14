import json
import os

class MerchantMap:
    def __init__(self, filepath='merchant_map.json'):
        self.filepath = filepath
        self.map = {}
        self.load()

    def load(self):
        if os.path.exists(self.filepath):
            with open(self.filepath, 'r', encoding='utf-8') as f:
                self.map = json.load(f)
        else:
            self.map = {}

    def save(self):
        with open(self.filepath, 'w', encoding='utf-8') as f:
            json.dump(self.map, f, ensure_ascii=False, indent=2)

    def get(self, merchant):
        # 返回标准名，找不到就返回原名
        return self.map.get(merchant, merchant)

    def add(self, variant, standard):
        self.map[variant] = standard
        self.save()

    def remove(self, variant):
        if variant in self.map:
            del self.map[variant]
            self.save()

    def update(self, variant, new_standard):
        self.map[variant] = new_standard
        self.save()

    def list_all(self):
        return self.map.copy()




class CategoryConfig:
    def __init__(self, filepath='category.json'):
        self.filepath = filepath
        self.categories = {}
        self.load()

    def load(self):
        if os.path.exists(self.filepath):
            with open(self.filepath, 'r', encoding='utf-8') as f:
                self.categories = json.load(f)
        else:
            self.categories = {}

    def save(self):
        with open(self.filepath, 'w', encoding='utf-8') as f:
            json.dump(self.categories, f, ensure_ascii=False, indent=2)

    def add_keyword(self, category, keyword):
        if category not in self.categories:
            self.categories[category] = []
        if keyword not in self.categories[category]:
            self.categories[category].append(keyword)
            self.save()

    def remove_keyword(self, category, keyword):
        if category in self.categories and keyword in self.categories[category]:
            self.categories[category].remove(keyword)
            self.save()

    def add_category(self, category):
        if category not in self.categories:
            self.categories[category] = []
            self.save()

    def remove_category(self, category):
        if category in self.categories:
            del self.categories[category]
            self.save()

    def list_all(self):
        return self.categories.copy()

# # 商户标准化
# merchant_map = MerchantMap('merchant_map.json')
# merchant_map.add('RCSS', 'SUPERSTORE')
# merchant_map.update('REAL CDN', 'SUPERSTORE')
# merchant_map.remove('PC EXPRESS')
# print(merchant_map.list_all())

# # 分类关键词
# cat_cfg = CategoryConfig('category.json')
# cat_cfg.add_category('Entertainment')
# cat_cfg.add_keyword('Supermarket', 'WALMART.CA')
# cat_cfg.remove_keyword('Supermarket', 'SAFEWAY')
# cat_cfg.remove_category('Online Shopping')
# print(cat_cfg.list_all())