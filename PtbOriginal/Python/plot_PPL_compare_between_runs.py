# authors : Wim Boes & Robbe Van Rompaey
# date: 12-10-2016 

# imports
from __future__ import absolute_import
from __future__ import division
from __future__ import print_function
import os
import sys
import numpy as np
import matplotlib.pyplot as plt
import argparse

python_path = os.path.abspath(os.getcwd())
general_path = os.path.split(python_path)[0]
input_path = os.path.join(general_path,'Output')
output_path = os.path.join(general_path,'Output/Figures')

#parser = argparse.ArgumentParser(description='Print comparation of train-, valid or test-PPL of certain runs')
#parser.add_argument("test_name", help="give the name of the test you wan't to show")
#parser.add_argument("num_run_start", help="give the startnumber of the tests you wan't to compare",
#                    type=int)
#parser.add_argument("num_run_end", help="give the endnumber of the tests you wan't to compare",
#                    type=int)
#parser.add_argument("train_valid_test", help="compare train, valid or test")
#args = parser.parse_args()

def plot_compare_between_runs(test_name, num_run_start, num_run_end, train_valid_test, input_path, output_path):
    train_valid_test_str = train_valid_test + '_np'
    fig = plt.figure()
    fig.suptitle('Compare '+train_valid_test+ ' plot of ' + test_name + ' from ' + str(num_run_start) + ' to ' + str(num_run_end), fontsize=14, fontweight='bold')
    
    colors = ['blue','green','red','purple','black','pink','orange','brown','yellow']
    linestyles = ['--'] #['-','dashed', 'dashdot']
    ax = fig.add_subplot(111)
    fig.subplots_adjust(top=0.86)
    ax.set_xlabel('Steps')
    ax.set_ylabel('Perplexity')
    
    min_lims = np.zeros(num_run_end-num_run_start+1)
    max_lims = np.zeros(num_run_end-num_run_start+1)
    
    param = test_name.split('-')
    
    data = np.load(input_path + '/' + test_name + '_'+ str(num_run_start)+ '/results' +'.npz')
    data_np = data[train_valid_test_str]
    data_steps = np.array([data_np[i][0]+data_np[i][1] for i in range(0,len(data_np))])
    data_PPL = np.array([data_np[i][2] for i in range(0,len(data_np))])
    min_lims[0] = np.min(data_PPL)-5
    max_lims[0] = np.percentile(data_PPL,85)
        
    label = ''
    title = ''
    param_np = data['param_train_np']
    for i in range(0,len(param_np)):
        if param_np[i][0] in param:
            label = label +param_np[i][0] + ' = ' + param_np[i][1] + ', '
        else:
            title = title +param_np[i][0] + ' = ' + param_np[i][1] + ', '
        if (i+1) % 4 == 0:
            title = title + '\n'
    while label[-1] != ',':
	label = label[:-1]
    label = label[:-1]
    while title[-1] != ',':
	title = title[:-1]
    title = title[:-1]
    
    if train_valid_test == 'test':
        ax.plot(data_steps, data_PPL, color=colors[num_run_start % len(colors)], marker='+', label = label)
    else:
        ax.plot(data_steps, data_PPL, color=colors[num_run_start % len(colors)], linestyle=linestyles[num_run_start % len(linestyles)], label = label)
    ax.set_title(title, fontsize=7)
    
    for run in range(num_run_start+1,num_run_end+1):
        data = np.load(input_path + '/' + test_name + '_'+ str(run)+ '/results' +'.npz')
        data_np = data[train_valid_test_str]
        
        data_steps = np.array([data_np[i][0]+data_np[i][1] for i in range(0,len(data_np))])
        data_PPL = np.array([data_np[i][2] for i in range(0,len(data_np))])
        min_lims[run-num_run_start] = np.min(data_PPL)-5
        max_lims[run-num_run_start] = np.percentile(data_PPL,85)

        label = ''
        param_np = data['param_train_np']
        for i in range(0,len(param_np)):
            if param_np[i][0] in param:
                label = label +param_np[i][0] + ' = ' + param_np[i][1] + ', '
        label = label[:-2]
        if train_valid_test == 'test':
            ax.plot(data_steps, data_PPL, color=colors[run % len(colors)], marker='+', label = label)    
        else:
            ax.plot(data_steps, data_PPL, color=colors[run % len(colors)], linestyle=linestyles[run % len(linestyles)], label = label)
    
    plt.ylim([np.min(min_lims),np.max(max_lims)])
    ax.legend(loc='upper right', fontsize=8)
    fig.savefig(output_path + '/' + test_name + '_from_' + str(num_run_start) + '_to_' + str(num_run_end) + '_' +train_valid_test+ '.png')
    plt.close()

def plot_compare_between_runs_summary(test_name, num_run_start, num_run_end, input_path, output_path):
    ###################################################
    # line chart
    ###################################################

    fig=plt.figure()
    ax = plt.subplot(111)
    
    colors = ['blue','green','red','purple','black','pink','orange','brown','cyan','yellow']
    linestyles = ['-'] #['-','dashed', 'dashdot']
 
    min_lims = np.zeros(num_run_end-num_run_start+1)
    max_lims = np.zeros(num_run_end-num_run_start+1)
    
    

    #load data
    data = np.load(input_path + '/' + test_name + '_'+ str(num_run_start)+ '/results' +'.npz')
    valid_np = data['valid_np']
    test_np = data['test_np']

    data_steps = np.array([valid_np[i][0]+valid_np[i][1] for i in range(0,len(valid_np))])
    valid_PPL = np.array([valid_np[i][2] for i in range(0,len(valid_np))])
    test_PPL = test_np[0][2] +0*data_steps

    min_lims[0] = np.min(np.concatenate((valid_PPL,test_PPL),axis=0))-5
    max_lims[0] = np.percentile(np.concatenate((valid_PPL,test_PPL),axis=0),95)
        
    label = ''
    title = ''
    param = test_name.split('-')
    param_np = data['param_train_np']
    for i in range(0,len(param_np)):
        if param_np[i][0] in param:
            label = label +param_np[i][0] + ' = ' + param_np[i][1] + ', '
        else:
            title = title +param_np[i][0] + ' = ' + param_np[i][1] + ', '
        if (i+1) % 4 == 0:
            title = title + '\n'
    while label[-1] != ',':
	label = label[:-1]
    label = label[:-1]
    while title[-1] != ',':
	title = title[:-1]
    title = title[:-1]
    
    ax.plot(data_steps, test_PPL, color=colors[num_run_start % len(colors)], linestyle='--')
    ax.plot(data_steps, valid_PPL, color=colors[num_run_start % len(colors)], linestyle='-', label = label)
    
    for run in range(num_run_start+1,num_run_end+1):
        data = np.load(input_path + '/' + test_name + '_'+ str(run)+ '/results' +'.npz')
        valid_np = data['valid_np']
    	test_np = data['test_np']
        
        data_steps = np.array([valid_np[i][0]+valid_np[i][1] for i in range(0,len(valid_np))])
        valid_PPL = np.array([valid_np[i][2] for i in range(0,len(valid_np))])
        test_PPL = test_np[0][2] +0*data_steps

        min_lims[run-num_run_start] = np.min(np.concatenate((valid_PPL,test_PPL),axis=0))-5
        max_lims[run-num_run_start] = np.percentile(np.concatenate((valid_PPL,test_PPL),axis=0),95)

        label = ''
        param_np = data['param_train_np']
        for i in range(0,len(param_np)):
            if param_np[i][0] in param:
                label = label +param_np[i][0] + ' = ' + param_np[i][1] + ', '
        label = label[:-2]
        
        ax.plot(data_steps, test_PPL, color=colors[run % len(colors)], linestyle='--')    
        ax.plot(data_steps, valid_PPL, color=colors[run % len(colors)], linestyle='-', label = label)

    fig.suptitle('Compare valid en test plot of ' + test_name + ' from ' + str(num_run_start) + ' to ' + str(num_run_end), fontsize=14, fontweight='bold')
    ax.set_title(title, fontsize=7)
    plt.subplots_adjust(top=.855, bottom=.25)
    ax.set_xlabel('Epochs')
    ax.set_ylabel('PPL')
    plt.ylim([np.min(min_lims),np.max(max_lims)])
    ax.legend(loc='upper center', bbox_to_anchor=(0.5, -0.11), ncol=2, fontsize=8)
    fig.savefig(output_path + '/' + test_name + '_from_' + str(num_run_start) + '_to_' + str(num_run_end) + '_val_test.png')
    plt.close()

def main():
    plot_compare_between_runs(args.test_name, args.num_run_start, args.num_run_end, args.train_valid_test, input_path, output_path)

if __name__ == "__main__":
    main()


