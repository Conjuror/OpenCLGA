#!/usr/bin/python3

import os
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import math
import time
import utils
import numpy
import pyopencl as cl


def get_context():
    contexts = []
    platforms = cl.get_platforms()
    for platform in platforms:
        devices = platform.get_devices()
        for device in devices:
            try:
                context = cl.Context(devices=[device])
                contexts.append(context)
            except:
                print("Can NOT create context from P(%s)-D(%s)"%(platform, device))
                continue
    return contexts[0] if len(contexts) > 0 else None

def build_program(ctx, filename):
    prog = None
    try:
        f = open(filename, "r")
        fstr = "".join(f.readlines())
        f.close()
        # -Werror : Make all warnings into errors.
        # https://www.khronos.org/registry/OpenCL/sdk/2.0/docs/man/xhtml/clBuildProgram.html
        prog = cl.Program(ctx, fstr).build(options=['-Werror'], cache_dir=None);
    except:
        import traceback
        traceback.print_exc()
    return prog

def create_queue(ctx):
    return cl.CommandQueue(ctx)

def create_bytearray(ctx, size):
    mf = cl.mem_flags
    py_buffer = numpy.zeros(size, dtype=numpy.int32)
    cl_buffer = cl.Buffer(ctx,
                          mf.READ_WRITE | mf.COPY_HOST_PTR,
                          hostbuf=py_buffer)
    return py_buffer, cl_buffer

def get_work_item_dimension(ctx):
    from pyopencl import context_info as ci
    from pyopencl import device_info as di
    devices = ctx.get_info(ci.DEVICES)
    assert len(devices) == 1
    dev = devices[0]
    # print("Max WI Dimensions : {}".format(dev.get_info(di.MAX_WORK_ITEM_DIMENSIONS)))
    WGSize = dev.get_info(di.MAX_WORK_GROUP_SIZE)
    WISize = dev.get_info(di.MAX_WORK_ITEM_SIZES)
    print("Max WG Size : {}".format(WGSize))
    print("Max WI Size : {}".format(WISize))
    return WGSize, WISize

if __name__ == "__main__":
    ctx = get_context()
    prog = build_program(ctx, "test_private.c")
    cwg, pwgs, lm, pm = None, None, None, None
    if ctx and prog:
        cwg, pwgs, lm, pm = utils.calculate_estimated_kernel_usage(prog, ctx, ["private_add"])
    else:
        print("Nothing is calculated !")

    queue = create_queue(ctx)

    min_time = None
    min_time_gws = None
    min_time_lws = None

    max_wgsize, wisize = get_work_item_dimension(ctx)
    total_WorkItems = 256
    assert total_WorkItems <= wisize[0] * wisize[1] * wisize[2]
    py_in, dev_in = create_bytearray(ctx, total_WorkItems)
    py_out, dev_out = create_bytearray(ctx, total_WorkItems)

    iter_global_WIs= int(math.log(total_WorkItems, 2))
    for g_factor in range(iter_global_WIs+1):
        print("=========================================== ")
        g_f_x = int(math.pow(2, g_factor))
        g_wi_size = (int(total_WorkItems/g_f_x), g_f_x, )
        print(" Global Work Group Size : {}".format(g_wi_size))
        # https://software.intel.com/sites/landingpage/opencl/optimization-guide/Work-Group_Size_Considerations.htm
        recommended_wi_per_group = 16
        iterations = int(math.log(recommended_wi_per_group, 2))
        for factor in range(iterations+1):
            print("-------- ")
            f_x = int(math.pow(2, factor))
            l_wi_size = (int(recommended_wi_per_group/f_x), f_x, )
            print(" Local Work Group Size : {}".format(l_wi_size))

            divided_wg_info = [int(gwi/l_wi_size[idx]) for idx, gwi in enumerate(g_wi_size)]
            print(" Divided Work Groups Info : {}".format(divided_wg_info))
            start_time = time.perf_counter()
            prog.private_add(queue, g_wi_size, l_wi_size, numpy.int32(total_WorkItems),
                             dev_in, dev_out).wait()

            elapsed_time = time.perf_counter() - start_time
            if not min_time:
                min_time = elapsed_time
                min_time_gws = g_wi_size
                min_time_lws = l_wi_size
            else:
                if elapsed_time <= min_time:
                    min_time = elapsed_time
                    min_time_gws = g_wi_size
                    min_time_lws = l_wi_size

    print(" Best Global WI Info : {}".format(min_time_gws))
    print(" Best Local WI Info : {}".format(min_time_lws))
    print(" Best Elapsed Time : {}".format(min_time))
    cl.enqueue_read_buffer(queue, dev_out, py_out)
    print(py_out)