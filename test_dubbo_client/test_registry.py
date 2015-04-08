from dubbo_client.registry import zk

__author__ = 'caozupeng'

if __name__ == '__main__':
    if zk.exists("/dubbo"):
        # Print the version of a node and its data
        children = zk.get_children("/dubbo")
        print "There are {0} children".format(len(children))
        for node in children:
            print node