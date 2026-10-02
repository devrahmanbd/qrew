package com.workflow.stream

import android.graphics.Paint
import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import android.widget.CheckBox
import android.widget.TextView
import androidx.recyclerview.widget.DiffUtil
import androidx.recyclerview.widget.ListAdapter
import androidx.recyclerview.widget.RecyclerView
import com.workflow.stream.data.TaskItem

class TaskAdapter(
    private val onTaskToggled: (TaskItem, Boolean) -> Unit
) : ListAdapter<TaskItem, TaskAdapter.TaskViewHolder>(TaskDiffCallback()) {

    override fun onCreateViewHolder(parent: ViewGroup, viewType: Int): TaskViewHolder {
        val view = LayoutInflater.from(parent.context).inflate(R.layout.item_task, parent, false)
        return TaskViewHolder(view)
    }

    override fun onBindViewHolder(holder: TaskViewHolder, position: Int) {
        holder.bind(getItem(position))
    }

    inner class TaskViewHolder(itemView: View) : RecyclerView.ViewHolder(itemView) {
        private val checkBox: CheckBox = itemView.findViewById(R.id.taskCheckBox)
        private val textView: TextView = itemView.findViewById(R.id.taskText)
        private val tagView: TextView = itemView.findViewById(R.id.taskTag)

        fun bind(task: TaskItem) {
            textView.text = task.text
            checkBox.isChecked = task.completed

            if (task.completed) {
                textView.paintFlags = textView.paintFlags or Paint.STRIKE_THRU_TEXT_FLAG
                textView.alpha = 0.5f
            } else {
                textView.paintFlags = textView.paintFlags and Paint.STRIKE_THRU_TEXT_FLAG.inv()
                textView.alpha = 1.0f
            }

            if (task.section.isNotEmpty()) {
                tagView.visibility = View.VISIBLE
                tagView.text = task.section.replace(Regex("^#+\s*"), "")
            } else {
                tagView.visibility = View.GONE
            }

            checkBox.setOnClickListener {
                val newStatus = checkBox.isChecked
                onTaskToggled(task, newStatus)
            }
        }
    }

    class TaskDiffCallback : DiffUtil.ItemCallback<TaskItem>() {
        override fun areItemsTheSame(oldItem: TaskItem, newItem: TaskItem): Boolean {
            return oldItem.lineNumber == newItem.lineNumber && oldItem.text == newItem.text
        }

        override fun areContentsTheSame(oldItem: TaskItem, newItem: TaskItem): Boolean {
            return oldItem == newItem
        }
    }
}
