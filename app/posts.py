#! /usr/bin/python

import couchdb
import mistune

from json import dumps
from collections import defaultdict

from werkzeug.local import Local, LocalProxy, LocalManager
from couchdb.http import ResourceConflict, ResourceNotFound
from flask import jsonify, g
from flask_marshmallow import Marshmallow
from itertools import chain

def get_mistune():
    markdown = getattr(g, "markdown", None)
    if markdown is None:
        markdown = g._markdown = mistune.Markdown()
    return markdown

markdown = LocalProxy(get_mistune)

class Posts:
    def __init__(self, user, password, name, host=None, port=None):
        if host is None:
            host = "127.0.0.1"
        if port is None:
            port = "5984"

        host = "127.0.0.1"
        port = "5984"

        self.client = couchdb.Server("http://%s:%s" % (host, port))

        self.client.credentials = (user, password)

        self.db = self.client[name]

        self.iterpost = self.postIterator("blogPosts/blog-posts")

    def savepost(self,
                 title="",
                 content="",
                 author="",
                 categories=[],
                 _id=False,
                 draft=True):
        """
        Save a post
        """
        if _id:
            doc = self.db[_id]
            doc["title"] = title
            doc["content"] = content
            doc["author"] = author
            doc["categories"] = categories
            doc["_id"] = _id
            doc["draft"] = draft
        else:
            doc = {
                    "title" : title,
                    "content" : content,
                    "author" : author,
                    "categories" : categories,
                    "type" : "post",
                    "draft" : draft
                    }


        print("post was saved %s" % doc)
        return jsonify(self.db.save(doc))

    def getpost(self,
                _id,
                json=True,
                convert=True,
                unpublished=False):
        """
        Get a post by id
        """
        if unpublished:
            results = self.db.iterview("blogPosts/unpublished", 1, include_docs=True, startkey=_id)
        else:
            results = self.db.iterview("blogPosts/blog-posts", 1, include_docs=True, startkey=_id)

        post = [result.doc for result in results][0]

        post["content"] = markdown(post["content"]) if convert else post["content"]

        return jsonify(post) if json else post

    def getinitial(self):
        """
        Get the initial post to start from
        """
        results = list(self.db.iterview("blogPosts/blog-posts", 2, include_docs=True))

        posts = [result.doc for result in results]

        # if there are no posts, return a defaultdict instead
        if len(posts) == 0:
            return defaultdict(str)

        post = posts[0]

        post["content"] = markdown(post["content"])

        return post

    def postIterator(self, viewname):
        """
        Post pagination
        """
        def inner(endkey=False, startkey=False):
            if startkey and not endkey:
                results = self.db.iterview(viewname, 2, include_docs=True, startkey=startkey)
            elif endkey and not startkey:
                results = self.db.iterview(viewname, 1, include_docs=True, endkey=endkey)
            else:
                results = self.db.iterview(viewname, 2, include_docs=True)

            docs = [result.doc for result in results]

            for doc in docs:
                doc["content"] = markdown(doc["content"])

            if not docs:
                return jsonify("end")

            if endkey and not startkey:
                if len(docs) < 2 or docs[0] == endkey:
                    return jsonify("start")
                return jsonify(docs[-2])

            if len(docs) == 1:
                return jsonify(docs[0])

            if docs:
                # if no startkey or endkey were specified, return the 0th post
                return jsonify(docs[1 if startkey else 0])

            return jsonify("end")
        return inner

    def allposts(self):
        """
        Gets all of the post IDs in the database. May be inefficient.
        """
        result = self.db.iterview("blogPosts/unpublished", 10, include_docs=True)

        posts = []
        for item in result:
            posts.append({
                            "_id" : item.doc["_id"],
                            "title" : item.doc["title"],
                            "author" : item.doc["author"]
                        })

        return jsonify(posts)

    def links(self, json=True):
        """
        Get the links we want to show
        """
        result = list(self.db.iterview("blogPosts/links", 1, include_docs=True))

        # make sure there are results
        if len(result) >= 1:
            xs = result[0].doc.get("links", [])
            return jsonify(xs) if json else xs
        return []

    def delete(self, _id):
        doc = self.db[_id]
        try:
            self.db.delete(doc)
            return jsonify(True)
        except (ResourceNotFound, ResourceConflict) as e:
            print(e)
            return jsonify(False)

    def categories(self):
        """
        Get the full list of all categories
        """
        # the view returns a list of lists of category names
        # we want to get the unique ones in a flat list
        return list(set(chain.from_iterable([
                    c["key"][1] for c in
                        self.db.view("blogPosts/categories",
                                     startkey=["categories"],
                                     startkey_docid=["categories"],
                                     endkey=["categories", {}],
                                     inclusive_end=False,
                                     reduce=True,
                                     group_level=2,
                                     group=True)
                ])))

    def browse(self,
               limit,
               startkey=False,
               endkey=False,
               categories=[],
               json=True):

        args = {
                "num" : limit,
                "categories" : dumps(categories)
                }

        if startkey:
            args["startkey"] = startkey
            args["startkey_docid"] = startkey

        if endkey:
            args["endkey"] = endkey
            args["getlast"] = "true"

        results = self.db.list(
                    "blogPosts/categories",
                    "blogPosts/format",
                    **args)
        if len(results) == 0:
            return jsonify([])

        posts = []
        for categories, post in results[1].get("results", []):
            post["content"] = markdown(post["content"])
            posts.append([categories, post])
        return jsonify(posts) if json else posts
