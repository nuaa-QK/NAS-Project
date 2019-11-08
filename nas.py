import json
import time
import random
import os
from multiprocessing import Queue, Pool
# from tensorflow import set_random_seed

from enumerater import Enumerater
from communicator import Communicator
from evaluator import Evaluator
from info_str import (
	NAS_CONFIG,
	CUR_VER_DIR,
	EVALOG_PATH_TEM,
	NETWORK_INFO_PATH,
	WINNER_LOG_PATH,
	LOG_EVAINFO_TEM,
	LOG_EVAFAIL,
	LOG_WINNER_TEM,
	SYS_EVAFAIL,
	SYS_EVA_RESULT_TEM,
	SYS_ELIINFO_TEM,
	SYS_INIT_ING,
	SYS_I_AM_PS,
	SYS_I_AM_WORKER,
	SYS_ENUM_ING,
	SYS_SEARCH_BLOCK_TEM,
	SYS_WORKER_DONE,
	SYS_WAIT_FOR_TASK,
	SYS_CONFIG_ING,
	SYS_GET_WINNER,
	SYS_BEST_AND_SCORE_TEM,
	SYS_START_GAME_TEM,
	SYS_CONFIG_OPS_ING
)

os.environ["TF_CPP_MIN_LOG_LEVEL"] = "3"

# # TODO Fatal: Corenas can not get items in IDLE_GPUQ (Queue)
# IDLE_GPUQ = Queue()

MAIN_CONFIG = NAS_CONFIG['nas_main']

def _subproc_eva(params, eva, gpuq):
	ngpu = gpuq.get()
	start_time = time.time()

	try:
		# return score and pos
		if MAIN_CONFIG['eva_debug']:
			raise Exception()  # return random result
		score, pos = _gpu_eva(params, eva, ngpu)
	except Exception as e:
		print("ERROR: ", e)
		score = random.uniform(0, 0.1)
		# params = (graph, cell, nn_preblock, pos, ...)
		pos = params[3]
	finally:
		gpuq.put(ngpu)

	end_time = time.time()
	time_cost = end_time - start_time

	return score, time_cost, pos


def _gpu_eva(params, eva, ngpu, isbestNN=False):
	graph, cell, nn_pb, p_, r_, ft_sign, pl_ = params
	# params = (graph, cell, nn_preblock, pos,
	# round, finetune_signal, pool_len)

	os.environ['CUDA_VISIBLE_DEVICES'] = str(ngpu)
	with open(EVALOG_PATH_TEM.format(ngpu), 'w') as f:
		f.write(LOG_EVAINFO_TEM.format(
			len(nn_pb)+1, r_, p_, pl_
		))
		print("Eva: gpu %d training..." % ngpu)
		with open("testf.txt", "a") as ff:
			ff.write("Eva: gpu %d training..." % ngpu)
		score = eva.evaluate(
			graph, cell, nn_pb, is_bestNN=isbestNN, update_pre_weight=ft_sign, log_file=f)
	print("Eva completed")
	return score, p_


def _module_init():
	return Enumerater(), Evaluator(), Communicator('ps', '127.0.0.1:5000')


def _filln_queue(q, n):
	for i in range(n):
		q.put(i)

def _wait_for_event(event_func):
	# TODO replaced by multiprocessing.Event
	while event_func():
		print(SYS_WAIT_FOR_TASK)
		time.sleep(20)
	return

def _do_task(pool, cmnct, eva):
	result_list = []

	while not cmnct.task.empty():
		try:
			task_params = cmnct.task.get(timeout=1)
			print(task_params)
		except:
			break
		if MAIN_CONFIG['subp_debug']:
			result = _subproc_eva(task_params, eva, cmnct.idle_gpuq)
		else:
			result = pool.apply_async(
				_subproc_eva,
				(task_params, eva, cmnct.idle_gpuq))
		result_list.append(result)

	return result_list

# TODO too slow
def _arrange_result(result_list, cmnct):
	_cnt = 0
	for r_ in result_list:
		_cnt += 1
		cplt_r = _cnt / len(result_list) * 100
		if MAIN_CONFIG['subp_debug']:
			score, time_cost, network_index = r_
		else:
			score, time_cost, network_index = r_.get()
		# print(SYS_EVA_RESULT_TEM.format(network_index, score, time_cost))
		print("_arrange_result Completed: {} %".format(cplt_r))
		cmnct.result.put((score, network_index, time_cost))
	print('done!')
	return


class Nas():
	def __init__(self):
		return

	def _ps_run(self, enum, eva, cmnct):
		print(SYS_ENUM_ING)

		import corenas
		network_pool_tem = enum.enumerate()
		for i in range(MAIN_CONFIG["block_num"]):
			print(SYS_SEARCH_BLOCK_TEM.format(i+1, MAIN_CONFIG["block_num"]))
			block, best_index = corenas.Corenas(i, eva, cmnct, network_pool_tem)
			block.pre_block.append([
				block.graph_part,
				block.graph_full_list[best_index],
				block.cell_list[best_index]
			])
		cmnct.end_flag.put(1)  # TODO find other way to stop workers

		return block.pre_block

	def _worker_run(eva, cmnct):
		_filln_queue(cmnct.idle_gpuq, NAS_CONFIG["num_gpu"])
		with Pool(processess=NAS_CONFIG["num_gpu"]) as pool:
			while cmnct.end_flag.empty():
				_wait_for_event(cmnct.data_sync.empty)

				cmnct.data_count += 1
				data_count_ps = cmnct.data_sync.get(timeout=1)
				eva.add_data(1600*(data_count_ps-cmnct.data_count+1))

				result_list = _do_task(pool, cmnct, eva)
				_arrange_result(result_list, cmnct)

				_wait_for_event(cmnct.task.empty)
		return

	def run(self):
		print(SYS_INIT_ING)
		enum, eva, cmnct = _module_init()

		if NAS_CONFIG['cmnct']['is_ps']:
			print(SYS_I_AM_PS)
			return self._ps_run(enum, eva, cmnct)
		else:
			print(SYS_I_AM_WORKER)
			self._worker_run(eva, cmnct)
			print(SYS_WORKER_DONE)

		return
	def run_global(self):
		enum, eva ,cmnct= _module_init()
		import glo_corenas
		glo_corenas.dis_global(enum,eva,NAS_CONFIG['num_gpu'])

if __name__ == '__main__':
	nas = Nas()
	nas.run_global()
