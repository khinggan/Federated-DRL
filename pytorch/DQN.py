import numpy as np
import torch 
from tqdm import tqdm

class Agent():
    def __init__(self, env_fn, Qnet, buffer, net_args,
                 max_epsilon, min_epsilon,  
                 gamma, decay_steps,
                 target_update_rate, min_buffer) -> None:
        
        self.env = env_fn()
        self.env_test = env_fn()
        self.n_actions = self.env.action_space.n
        self.state_shape = self.env.observation_space.shape

        self.online_net = Qnet(self.state_shape[0], self.n_actions, **net_args)
        self.target_net = Qnet(self.state_shape[0], self.n_actions, **net_args)
        self.update_target_network()

        self.buffer = buffer(self.state_shape, self.n_actions)
        self.min_buffer = min_buffer

        self.epsilon = max_epsilon
        self.min_epsilon = min_epsilon
        self.epsilon_decay = (max_epsilon - min_epsilon)/decay_steps
        self.gamma = gamma
        self.target_update_rate = target_update_rate

        self.step_count = 0
        self.episode_reward = 0
        self.episode_count = 1
        self.state = self.env.reset()
        self.rewards = []


    def step(self, steps):
        for _ in range(steps):
            self.step_count += 1
            action = self.epsilonGreedyPolicy(self.state)
            state_p, reward, terminated, truncated, info = self.env.step(action) # observation, reward, terminated, truncated, info
            self.episode_reward += reward

            # is_truncated = 'TimeLimit.truncated' in info and info['TimeLimit.truncated']
            # is_failure = done and not is_truncated

            done = terminated or truncated
            is_failure = done and not truncated
            self.buffer.store(self.state, action, reward, state_p, float(is_failure))

            if len(self.buffer) >= self.min_buffer:
                self.update()
                if self.step_count % self.target_update_rate == 0:
                    self.update_target_network()

            self.state = state_p
            if done:
                self.episode_count += 1
                self.state = self.env.reset()
                self.rewards.append(self.episode_reward)
                self.episode_reward = 0


    def train(self, n_episodes):
        for _ in range(n_episodes):
            self.episode_reward = 0
            self.state = self.env.reset()

            while True:
                self.step_count += 1
                action = self.epsilonGreedyPolicy(self.state)
                state_p, reward, done, info = self.env.step(action)
                self.episode_reward += reward

                is_truncated = 'TimeLimit.truncated' in info and info['TimeLimit.truncated']
                is_failure = done and not is_truncated
                self.buffer.store(self.state, action, reward, state_p, float(is_failure))

                if len(self.buffer) >= self.min_buffer:
                    self.update()
                    if self.step_count % self.target_update_rate == 0:
                        self.update_target_network()

                self.state = state_p
                if done:
                    print(self.episode_reward)
                    self.episode_count += 1
                    self.rewards.append(self.episode_reward)
                    break


    def get_score(self):
        return np.mean(self.rewards[-5:])


    def evaluate(self):
        rewards = 0
        state = self.env_test.reset()
        while True:
            if type(state) == tuple:
                state = state[0]
            action = self.greedyPolicy(state)
            state_p, reward, terminated, truncated, info = self.env_test.step(action)    # observation, reward, terminated, truncated, info

            done = terminated or truncated
            rewards += reward
            if done:
                break
            state = state_p
        return rewards


    def update(self):
        states, actions, rewards, states_p, is_terminals = self.buffer.sample()
        actions = torch.tensor(actions)
        is_terminals = torch.tensor(is_terminals)
        rewards = torch.tensor(rewards)
        q_states = self.online_net(states).gather(1, actions).squeeze()
        with torch.no_grad():
            q_states_p = self.target_net(states_p)
        q_target = rewards + self.gamma * (1-is_terminals) * q_states_p.max(1)[0]

        td_error = q_states - q_target
        loss = td_error.pow(2).mean()

        self.online_net.optimize(loss)


    def update_epsilon(self):
        self.epsilon = max(self.min_epsilon, 
                           self.epsilon - self.epsilon_decay)


    def update_target_network(self):
        self.target_net.load_state_dict(self.online_net.state_dict())


    def epsilonGreedyPolicy(self, state):
        if np.random.rand() < self.epsilon:
            action = np.random.randint(self.n_actions)
        else:
            with torch.no_grad():
                action = self.online_net(state).argmax().item()
        self.update_epsilon()
        return action

    
    def greedyPolicy(self, state):
        with torch.no_grad():
            action = self.target_net(state).argmax()
        return action.item()