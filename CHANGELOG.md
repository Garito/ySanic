# ySanic's Change Log
## 0.1.0
This version has three main differences:
- Introspection
- No decorators except notaroute
- Jinja2 emails

### Introspection
This is the biggest change since it allows several things:
- Automatic route generator
- Does the hard work for OpenApi since, in this version is key to achieve Full stack features

It uses the models' decorators to determine if a model's member is a route (when it has ```consumes``` and/or ```produces```) and what kind of route is (if it has ```consumes``` is a in route if not is and out one)

That allow us to focus in the definition of the problem's domain

### No decorators except notaroute
The only point of the decorators of ySanic was to allow to customize the response of the route but since yREST is based on REST it make sense to simplify this facet

You can always eject from yRest and use the manual routes with full control

So notaroute is the way to exclude members of the model that uses ```consumes```/```produces``` but maintain the convenience of this decorators (in terms of automatic validation and so on)

### Jinja2 emails
Anyone that has deal with emails know the nightmare they are so introducing jinja2 as a template system only simplifys what its is difficult as it is
